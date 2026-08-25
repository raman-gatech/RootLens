"""Incident intake and evidence-grounded investigation endpoints."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field, model_validator

from rootlens.investigation import (
    AgentMode,
    Evidence,
    HistoricalIncident,
    Hypothesis,
    Incident,
    IncidentSeverity,
    Investigation,
    SimilarIncident,
)
from rootlens.investigation.contracts import Alert, InvestigationBudget
from rootlens.investigation.errors import IncidentNotFoundError, InvestigationError
from rootlens.investigation.service import InvestigationService
from rootlens.telemetry import QueryWindow
from rootlens.topology import ServiceGraphSnapshot

router = APIRouter(prefix="/api/v1", tags=["incidents"])


class CreateIncidentRequest(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    summary: str = Field(default="", max_length=4_000)
    affected_service: str | None = Field(default=None, max_length=120)
    severity: IncidentSeverity = IncidentSeverity.SEV2
    incident_start: datetime
    incident_end: datetime = Field(default_factory=lambda: datetime.now(UTC))
    labels: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_window(self) -> CreateIncidentRequest:
        window = QueryWindow(start=self.incident_start, end=self.incident_end)
        duration = window.end - window.start
        if duration < timedelta(minutes=2):
            raise ValueError("incident window must be at least two minutes")
        if duration > timedelta(hours=24):
            raise ValueError("incident window cannot exceed 24 hours")
        return self

    def to_incident(self) -> Incident:
        return Incident(
            title=self.title,
            summary=self.summary,
            affected_service=self.affected_service,
            severity=self.severity,
            window=QueryWindow(start=self.incident_start, end=self.incident_end),
            labels=self.labels,
        )


class InvestigateRequest(BaseModel):
    mode: AgentMode = AgentMode.MULTI
    budget: InvestigationBudget = Field(default_factory=InvestigationBudget)


class PrometheusAlert(BaseModel):
    status: str = "firing"
    labels: dict[str, str] = Field(default_factory=dict)
    annotations: dict[str, str] = Field(default_factory=dict)
    startsAt: datetime | None = None
    endsAt: datetime | None = None


class PrometheusWebhook(BaseModel):
    status: str = "firing"
    alerts: list[PrometheusAlert] = Field(min_length=1, max_length=100)


class IncidentDetail(BaseModel):
    incident: Incident
    latest_investigation: Investigation | None


class TimelineItem(BaseModel):
    timestamp: datetime
    category: str
    title: str
    details: dict[str, Any] = Field(default_factory=dict)


class RememberIncidentRequest(BaseModel):
    root_cause_service: str = Field(min_length=1, max_length=160)
    failure_mode: str = Field(min_length=1, max_length=240)
    resolution: str = Field(min_length=1, max_length=4_000)


def get_investigation_service(request: Request) -> InvestigationService:
    return cast(InvestigationService, request.app.state.investigation_service)


InvestigationServiceDependency = Annotated[InvestigationService, Depends(get_investigation_service)]


@router.post("/incidents", response_model=Incident, status_code=status.HTTP_201_CREATED)
async def create_incident(
    payload: CreateIncidentRequest, service: InvestigationServiceDependency
) -> Incident:
    return await service.create(payload.to_incident())


@router.post(
    "/alerts/prometheus", response_model=tuple[Incident, ...], status_code=status.HTTP_201_CREATED
)
async def ingest_prometheus_alerts(
    payload: PrometheusWebhook, service: InvestigationServiceDependency
) -> tuple[Incident, ...]:
    created: list[Incident] = []
    now = datetime.now(UTC)
    for alert in payload.alerts:
        start = alert.startsAt or now - timedelta(minutes=10)
        end = alert.endsAt or now
        if end - start < timedelta(minutes=2):
            start = end - timedelta(minutes=2)
        name = alert.labels.get("alertname", "Prometheus alert")
        summary = alert.annotations.get("description", alert.annotations.get("summary", ""))
        incident = await service.create(
            Incident(
                title=name,
                summary=summary,
                affected_service=alert.labels.get("service") or alert.labels.get("service_name"),
                severity=_severity(alert.labels.get("severity")),
                window=QueryWindow(start=start, end=end),
                labels=alert.labels,
            )
        )
        await service.record_alert(
            Alert(
                incident_id=incident.id,
                source="prometheus",
                status=alert.status,
                labels=alert.labels,
                annotations=alert.annotations,
                starts_at=start,
                ends_at=alert.endsAt,
            )
        )
        created.append(incident)
    return tuple(created)


@router.get("/incidents", response_model=tuple[Incident, ...])
async def list_incidents(
    service: InvestigationServiceDependency,
    limit: int = Query(default=100, ge=1, le=500),
) -> tuple[Incident, ...]:
    return await service.list(limit=limit)


@router.get("/incidents/{incident_id}", response_model=IncidentDetail)
async def get_incident(
    incident_id: UUID, service: InvestigationServiceDependency
) -> IncidentDetail:
    try:
        incident = await service.get(incident_id)
        latest = await service.latest(incident_id)
        return IncidentDetail(incident=incident, latest_investigation=latest)
    except IncidentNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post("/incidents/{incident_id}/investigate", response_model=Investigation)
async def investigate_incident(
    incident_id: UUID,
    payload: InvestigateRequest,
    service: InvestigationServiceDependency,
) -> Investigation:
    try:
        return await service.investigate(incident_id, mode=payload.mode, budget=payload.budget)
    except IncidentNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except InvestigationError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.get("/incidents/{incident_id}/hypotheses", response_model=tuple[Hypothesis, ...])
async def get_hypotheses(
    incident_id: UUID, service: InvestigationServiceDependency
) -> tuple[Hypothesis, ...]:
    latest = await _latest_or_404(service, incident_id)
    return latest.hypotheses


@router.get("/incidents/{incident_id}/evidence", response_model=tuple[Evidence, ...])
async def get_evidence(
    incident_id: UUID, service: InvestigationServiceDependency
) -> tuple[Evidence, ...]:
    latest = await _latest_or_404(service, incident_id)
    return latest.evidence


@router.get("/incidents/{incident_id}/graph", response_model=ServiceGraphSnapshot)
async def get_graph(
    incident_id: UUID, service: InvestigationServiceDependency
) -> ServiceGraphSnapshot:
    latest = await _latest_or_404(service, incident_id)
    if latest.graph is None:
        raise HTTPException(status_code=404, detail="investigation has no trace graph")
    return latest.graph


@router.get("/incidents/{incident_id}/timeline", response_model=tuple[TimelineItem, ...])
async def get_timeline(
    incident_id: UUID, service: InvestigationServiceDependency
) -> tuple[TimelineItem, ...]:
    latest = await _latest_or_404(service, incident_id)
    items = [
        TimelineItem(
            timestamp=item.observed_at,
            category="evidence",
            title=f"{item.source.value}: {item.signal}",
            details={"evidence_id": str(item.id), "service": item.service},
        )
        for item in latest.evidence
    ]
    items.extend(
        TimelineItem(
            timestamp=item.started_at,
            category="agent",
            title=item.agent_id.value,
            details={"status": item.status, "completed_at": item.completed_at.isoformat()},
        )
        for item in latest.agent_runs
    )
    return tuple(sorted(items, key=lambda item: (item.timestamp, item.title)))


@router.get("/incidents/{incident_id}/similar", response_model=tuple[SimilarIncident, ...])
async def get_similar_incidents(
    incident_id: UUID, service: InvestigationServiceDependency
) -> tuple[SimilarIncident, ...]:
    try:
        return await service.similar(incident_id)
    except IncidentNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post(
    "/incidents/{incident_id}/memory",
    response_model=HistoricalIncident,
    status_code=status.HTTP_201_CREATED,
)
async def remember_incident(
    incident_id: UUID,
    payload: RememberIncidentRequest,
    service: InvestigationServiceDependency,
) -> HistoricalIncident:
    try:
        return await service.remember(
            incident_id,
            root_cause_service=payload.root_cause_service,
            failure_mode=payload.failure_mode,
            resolution=payload.resolution,
        )
    except IncidentNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except InvestigationError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


async def _latest_or_404(service: InvestigationService, incident_id: UUID) -> Investigation:
    try:
        latest = await service.latest(incident_id)
    except IncidentNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    if latest is None:
        raise HTTPException(status_code=404, detail="incident has not been investigated")
    return latest


def _severity(value: str | None) -> IncidentSeverity:
    normalized = (value or "").lower()
    return {
        "critical": IncidentSeverity.SEV1,
        "sev1": IncidentSeverity.SEV1,
        "warning": IncidentSeverity.SEV3,
        "sev3": IncidentSeverity.SEV3,
        "info": IncidentSeverity.SEV4,
        "sev4": IncidentSeverity.SEV4,
    }.get(normalized, IncidentSeverity.SEV2)

"""HTTP endpoints for evidence-linked anomaly analysis and ranking."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, model_validator

from rootlens.anomaly import AnomalyAnalysisSnapshot, SignalName
from rootlens.anomaly.errors import AnomalyAnalysisError
from rootlens.anomaly.service import AnomalyAnalysisService
from rootlens.telemetry import QueryWindow

router = APIRouter(prefix="/api/v1/anomalies", tags=["anomalies"])


class AnomalyAnalyzeRequest(BaseModel):
    baseline_start: datetime
    baseline_end: datetime
    incident_start: datetime
    incident_end: datetime
    signals: tuple[SignalName, ...] = tuple(SignalName)
    step_seconds: int = Field(default=30, ge=10, le=300)
    minimum_score: float = Field(default=0.5, ge=0, le=1)

    @model_validator(mode="after")
    def validate_windows(self) -> AnomalyAnalyzeRequest:
        baseline = QueryWindow(start=self.baseline_start, end=self.baseline_end)
        incident = QueryWindow(start=self.incident_start, end=self.incident_end)
        if baseline.end > incident.start:
            raise ValueError("baseline window must end before or at incident start")
        if not self.signals:
            raise ValueError("at least one signal is required")
        if len(set(self.signals)) != len(self.signals):
            raise ValueError("signals must be unique")
        baseline_points = (
            int((baseline.end - baseline.start).total_seconds() / self.step_seconds) + 1
        )
        incident_points = (
            int((incident.end - incident.start).total_seconds() / self.step_seconds) + 1
        )
        if baseline_points < 8:
            raise ValueError("baseline window must contain at least 8 requested samples")
        if baseline_points > 5_000 or incident_points > 2_000:
            raise ValueError("requested anomaly analysis exceeds the sample limit")
        return self

    def baseline_window(self) -> QueryWindow:
        return QueryWindow(start=self.baseline_start, end=self.baseline_end)

    def incident_window(self) -> QueryWindow:
        return QueryWindow(start=self.incident_start, end=self.incident_end)


def get_anomaly_service(request: Request) -> AnomalyAnalysisService:
    return cast(AnomalyAnalysisService, request.app.state.anomaly_service)


AnomalyServiceDependency = Annotated[AnomalyAnalysisService, Depends(get_anomaly_service)]


@router.post(
    "/analyze",
    response_model=AnomalyAnalysisSnapshot,
    status_code=status.HTTP_201_CREATED,
)
async def analyze_anomalies(
    payload: AnomalyAnalyzeRequest,
    service: AnomalyServiceDependency,
) -> AnomalyAnalysisSnapshot:
    try:
        return await service.analyze(
            baseline_window=payload.baseline_window(),
            incident_window=payload.incident_window(),
            signals=payload.signals,
            step_seconds=payload.step_seconds,
            minimum_score=payload.minimum_score,
        )
    except AnomalyAnalysisError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)
        ) from error


@router.get("/latest", response_model=AnomalyAnalysisSnapshot)
async def latest_anomalies(service: AnomalyServiceDependency) -> AnomalyAnalysisSnapshot:
    snapshot = await service.latest()
    if snapshot is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="no anomaly analysis exists"
        )
    return snapshot

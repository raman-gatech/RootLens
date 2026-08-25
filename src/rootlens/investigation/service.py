"""Incident lifecycle and investigation application service."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from rootlens.investigation.agents import InvestigationRunner
from rootlens.investigation.contracts import (
    AgentMode,
    Alert,
    HistoricalIncident,
    Incident,
    IncidentStatus,
    Investigation,
    InvestigationBudget,
    InvestigationStatus,
    SimilarIncident,
)
from rootlens.investigation.errors import IncidentNotFoundError, InvestigationError
from rootlens.investigation.memory import IncidentMemory
from rootlens.investigation.repository import InvestigationRepository


class InvestigationService:
    def __init__(
        self,
        *,
        repository: InvestigationRepository,
        runner: InvestigationRunner,
        memory: IncidentMemory | None = None,
    ) -> None:
        self._repository = repository
        self._runner = runner
        self._memory = memory

    async def create(self, incident: Incident) -> Incident:
        return await self._repository.create_incident(incident)

    async def record_alert(self, alert: Alert) -> Alert:
        return await self._repository.save_alert(alert)

    async def list(self, *, limit: int = 100) -> tuple[Incident, ...]:
        return await self._repository.list_incidents(limit=limit)

    async def get(self, incident_id: UUID) -> Incident:
        incident = await self._repository.get_incident(incident_id)
        if incident is None:
            raise IncidentNotFoundError(f"incident {incident_id} does not exist")
        return incident

    async def latest(self, incident_id: UUID) -> Investigation | None:
        await self.get(incident_id)
        return await self._repository.latest_investigation(incident_id)

    async def investigate(
        self,
        incident_id: UUID,
        *,
        mode: AgentMode,
        budget: InvestigationBudget | None = None,
    ) -> Investigation:
        incident = await self.get(incident_id)
        investigating = incident.model_copy(
            update={"status": IncidentStatus.INVESTIGATING, "updated_at": datetime.now(UTC)}
        )
        await self._repository.save_incident(investigating)
        try:
            investigation = await self._runner.run(investigating, mode=mode, budget=budget)
        except Exception as error:
            reopened = investigating.model_copy(
                update={"status": IncidentStatus.OPEN, "updated_at": datetime.now(UTC)}
            )
            await self._repository.save_incident(reopened)
            if isinstance(error, InvestigationError):
                raise
            raise InvestigationError(f"investigation failed: {error}") from error
        await self._repository.save_investigation(investigation)
        final_status = (
            IncidentStatus.DIAGNOSED
            if investigation.status is InvestigationStatus.COMPLETED
            else IncidentStatus.OPEN
        )
        await self._repository.save_incident(
            investigating.model_copy(
                update={"status": final_status, "updated_at": datetime.now(UTC)}
            )
        )
        return investigation

    async def similar(self, incident_id: UUID) -> tuple[SimilarIncident, ...]:
        incident = await self.get(incident_id)
        if self._memory is None:
            return ()
        latest = await self._repository.latest_investigation(incident_id)
        evidence = latest.evidence if latest is not None else ()
        return await self._memory.similar(incident, evidence)

    async def remember(
        self,
        incident_id: UUID,
        *,
        root_cause_service: str,
        failure_mode: str,
        resolution: str,
    ) -> HistoricalIncident:
        if self._memory is None:
            raise InvestigationError("incident memory is not configured")
        incident = await self.get(incident_id)
        latest = await self._repository.latest_investigation(incident_id)
        historical = HistoricalIncident(
            source_incident_id=incident.id,
            title=incident.title,
            summary=incident.summary,
            root_cause_service=root_cause_service,
            failure_mode=failure_mode,
            resolution=resolution,
            services=tuple(
                sorted(
                    {
                        item.service
                        for item in (latest.evidence if latest else ())
                        if item.service is not None
                    }
                )
            ),
            symptoms=tuple(item.signal for item in (latest.evidence if latest else ())),
        )
        return await self._memory.remember(historical)

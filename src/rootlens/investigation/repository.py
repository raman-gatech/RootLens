"""PostgreSQL persistence for incidents and complete investigation snapshots."""

from __future__ import annotations

from uuid import UUID

import sqlalchemy as sa

from rootlens.db.session import Database
from rootlens.investigation.contracts import Alert, Incident, Investigation

_metadata = sa.MetaData()
_incidents = sa.Table(
    "incidents",
    _metadata,
    sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
    sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
    sa.Column("severity", sa.String(16), nullable=False),
    sa.Column("status", sa.String(32), nullable=False),
    sa.Column("affected_service", sa.String(160), nullable=True),
    sa.Column("snapshot", sa.JSON(), nullable=False),
)
_investigations = sa.Table(
    "investigations",
    _metadata,
    sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
    sa.Column("incident_id", sa.Uuid(as_uuid=True), nullable=False),
    sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("mode", sa.String(32), nullable=False),
    sa.Column("status", sa.String(32), nullable=False),
    sa.Column("provider", sa.String(80), nullable=False),
    sa.Column("snapshot", sa.JSON(), nullable=False),
)
_alerts = sa.Table(
    "alerts",
    _metadata,
    sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
    sa.Column("incident_id", sa.Uuid(as_uuid=True), nullable=False),
    sa.Column("source", sa.String(80), nullable=False),
    sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("payload", sa.JSON(), nullable=False),
)
_evidence = sa.Table(
    "evidence",
    _metadata,
    sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
    sa.Column("incident_id", sa.Uuid(as_uuid=True), nullable=False),
    sa.Column("investigation_id", sa.Uuid(as_uuid=True), nullable=False),
    sa.Column("source", sa.String(32), nullable=False),
    sa.Column("origin", sa.String(32), nullable=False),
    sa.Column("service", sa.String(160), nullable=True),
    sa.Column("query_reference", sa.String(1_000), nullable=False),
    sa.Column("payload", sa.JSON(), nullable=False),
)
_hypotheses = sa.Table(
    "hypotheses",
    _metadata,
    sa.Column("investigation_id", sa.Uuid(as_uuid=True), primary_key=True),
    sa.Column("hypothesis_id", sa.String(160), primary_key=True),
    sa.Column("incident_id", sa.Uuid(as_uuid=True), nullable=False),
    sa.Column("rank", sa.Integer(), nullable=False),
    sa.Column("status", sa.String(32), nullable=False),
    sa.Column("confidence", sa.Float(), nullable=False),
    sa.Column("payload", sa.JSON(), nullable=False),
)
_agent_runs = sa.Table(
    "agent_runs",
    _metadata,
    sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
    sa.Column("investigation_id", sa.Uuid(as_uuid=True), nullable=False),
    sa.Column("incident_id", sa.Uuid(as_uuid=True), nullable=False),
    sa.Column("agent_id", sa.String(64), nullable=False),
    sa.Column("payload", sa.JSON(), nullable=False),
)
_tool_calls = sa.Table(
    "tool_calls",
    _metadata,
    sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
    sa.Column("investigation_id", sa.Uuid(as_uuid=True), nullable=False),
    sa.Column("incident_id", sa.Uuid(as_uuid=True), nullable=False),
    sa.Column("agent_id", sa.String(64), nullable=False),
    sa.Column("tool_name", sa.String(120), nullable=False),
    sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("status", sa.String(16), nullable=False),
    sa.Column("payload", sa.JSON(), nullable=False),
)


class InvestigationRepository:
    def __init__(self, database: Database) -> None:
        self._database = database

    async def create_incident(self, incident: Incident) -> Incident:
        statement = sa.insert(_incidents).values(
            id=incident.id,
            created_at=incident.created_at,
            updated_at=incident.updated_at,
            window_start=incident.window.start,
            window_end=incident.window.end,
            severity=incident.severity.value,
            status=incident.status.value,
            affected_service=incident.affected_service,
            snapshot=incident.model_dump(mode="json"),
        )
        async with self._database.session() as session:
            await session.execute(statement)
            await session.commit()
        return incident

    async def save_alert(self, alert: Alert) -> Alert:
        async with self._database.session() as session:
            await session.execute(
                sa.insert(_alerts).values(
                    id=alert.id,
                    incident_id=alert.incident_id,
                    source=alert.source,
                    received_at=alert.received_at,
                    payload=alert.model_dump(mode="json"),
                )
            )
            await session.commit()
        return alert

    async def save_incident(self, incident: Incident) -> None:
        statement = (
            sa.update(_incidents)
            .where(_incidents.c.id == incident.id)
            .values(
                updated_at=incident.updated_at,
                status=incident.status.value,
                affected_service=incident.affected_service,
                snapshot=incident.model_dump(mode="json"),
            )
        )
        async with self._database.session() as session:
            await session.execute(statement)
            await session.commit()

    async def get_incident(self, incident_id: UUID) -> Incident | None:
        statement = sa.select(_incidents.c.snapshot).where(_incidents.c.id == incident_id)
        async with self._database.session() as session:
            result = await session.execute(statement)
            payload = result.scalar_one_or_none()
        return Incident.model_validate(payload) if payload is not None else None

    async def list_incidents(self, *, limit: int = 100) -> tuple[Incident, ...]:
        statement = (
            sa.select(_incidents.c.snapshot).order_by(_incidents.c.created_at.desc()).limit(limit)
        )
        async with self._database.session() as session:
            result = await session.execute(statement)
            payloads = result.scalars().all()
        return tuple(Incident.model_validate(payload) for payload in payloads)

    async def save_investigation(self, investigation: Investigation) -> None:
        snapshot = investigation.model_dump(mode="json")
        async with self._database.session() as session:
            await session.execute(
                sa.insert(_investigations).values(
                    id=investigation.id,
                    incident_id=investigation.incident_id,
                    started_at=investigation.started_at,
                    completed_at=investigation.completed_at,
                    mode=investigation.mode.value,
                    status=investigation.status.value,
                    provider=investigation.provider,
                    snapshot=snapshot,
                )
            )
            if investigation.evidence:
                await session.execute(
                    sa.insert(_evidence),
                    [
                        {
                            "id": item.id,
                            "incident_id": investigation.incident_id,
                            "investigation_id": investigation.id,
                            "source": item.source.value,
                            "origin": item.origin.value,
                            "service": item.service,
                            "query_reference": item.query_reference,
                            "payload": item.model_dump(mode="json"),
                        }
                        for item in investigation.evidence
                    ],
                )
            if investigation.hypotheses:
                await session.execute(
                    sa.insert(_hypotheses),
                    [
                        {
                            "investigation_id": investigation.id,
                            "hypothesis_id": item.id,
                            "incident_id": investigation.incident_id,
                            "rank": item.rank,
                            "status": item.status.value,
                            "confidence": item.confidence,
                            "payload": item.model_dump(mode="json"),
                        }
                        for item in investigation.hypotheses
                    ],
                )
            if investigation.agent_runs:
                await session.execute(
                    sa.insert(_agent_runs),
                    [
                        {
                            "id": item.id,
                            "investigation_id": investigation.id,
                            "incident_id": investigation.incident_id,
                            "agent_id": item.agent_id.value,
                            "payload": item.model_dump(mode="json"),
                        }
                        for item in investigation.agent_runs
                    ],
                )
            if investigation.tool_calls:
                await session.execute(
                    sa.insert(_tool_calls),
                    [
                        {
                            "id": item.id,
                            "investigation_id": investigation.id,
                            "incident_id": investigation.incident_id,
                            "agent_id": item.agent_id.value,
                            "tool_name": item.tool_name,
                            "started_at": item.started_at,
                            "status": item.status,
                            "payload": item.model_dump(mode="json"),
                        }
                        for item in investigation.tool_calls
                    ],
                )
            await session.commit()

    async def latest_investigation(self, incident_id: UUID) -> Investigation | None:
        statement = (
            sa.select(_investigations.c.snapshot)
            .where(_investigations.c.incident_id == incident_id)
            .order_by(_investigations.c.started_at.desc())
            .limit(1)
        )
        async with self._database.session() as session:
            result = await session.execute(statement)
            payload = result.scalar_one_or_none()
        return Investigation.model_validate(payload) if payload is not None else None

"""PostgreSQL persistence for immutable anomaly-analysis snapshots."""

import sqlalchemy as sa

from rootlens.anomaly.contracts import AnomalyAnalysisSnapshot
from rootlens.db.session import Database

_metadata = sa.MetaData()
_analyses = sa.Table(
    "telemetry_anomalies",
    _metadata,
    sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
    sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("baseline_start", sa.DateTime(timezone=True), nullable=False),
    sa.Column("baseline_end", sa.DateTime(timezone=True), nullable=False),
    sa.Column("incident_start", sa.DateTime(timezone=True), nullable=False),
    sa.Column("incident_end", sa.DateTime(timezone=True), nullable=False),
    sa.Column("evaluated_series", sa.Integer(), nullable=False),
    sa.Column("anomaly_count", sa.Integer(), nullable=False),
    sa.Column("snapshot", sa.JSON(), nullable=False),
)


class AnomalyRepository:
    def __init__(self, database: Database) -> None:
        self._database = database

    async def save(self, snapshot: AnomalyAnalysisSnapshot) -> None:
        statement = sa.insert(_analyses).values(
            id=snapshot.id,
            generated_at=snapshot.generated_at,
            baseline_start=snapshot.baseline_window.start,
            baseline_end=snapshot.baseline_window.end,
            incident_start=snapshot.incident_window.start,
            incident_end=snapshot.incident_window.end,
            evaluated_series=snapshot.evaluated_series,
            anomaly_count=len(snapshot.anomalies),
            snapshot=snapshot.model_dump(mode="json"),
        )
        async with self._database.session() as session:
            await session.execute(statement)
            await session.commit()

    async def latest(self) -> AnomalyAnalysisSnapshot | None:
        statement = (
            sa.select(_analyses.c.snapshot).order_by(_analyses.c.generated_at.desc()).limit(1)
        )
        async with self._database.session() as session:
            result = await session.execute(statement)
            payload = result.scalar_one_or_none()
        if payload is None:
            return None
        return AnomalyAnalysisSnapshot.model_validate(payload)

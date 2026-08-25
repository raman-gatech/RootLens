"""Persistence for publishable aggregate evaluation reports."""

import sqlalchemy as sa

from rootlens.db.session import Database
from rootlens.evaluation import EvaluationReport

_metadata = sa.MetaData()
_runs = sa.Table(
    "evaluation_runs",
    _metadata,
    sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
    sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("dataset_version", sa.String(120), nullable=False),
    sa.Column("execution_mode", sa.String(40), nullable=False),
    sa.Column("incident_count", sa.Integer(), nullable=False),
    sa.Column("report", sa.JSON(), nullable=False),
)


class EvaluationRepository:
    def __init__(self, database: Database) -> None:
        self._database = database

    async def save(self, report: EvaluationReport) -> EvaluationReport:
        async with self._database.session() as session:
            await session.execute(
                sa.insert(_runs).values(
                    id=report.id,
                    generated_at=report.generated_at,
                    dataset_version=report.dataset_version,
                    execution_mode=report.execution_mode,
                    incident_count=report.incident_count,
                    report=report.model_dump(mode="json"),
                )
            )
            await session.commit()
        return report

    async def list(self, *, limit: int = 20) -> tuple[EvaluationReport, ...]:
        statement = sa.select(_runs.c.report).order_by(_runs.c.generated_at.desc()).limit(limit)
        async with self._database.session() as session:
            payloads = (await session.execute(statement)).scalars().all()
        return tuple(EvaluationReport.model_validate(payload) for payload in payloads)

"""Persistence for remediation proposals and immutable action receipts."""

from uuid import UUID

import sqlalchemy as sa

from rootlens.db.session import Database
from rootlens.remediation.contracts import (
    RemediationAction,
    RemediationPlan,
    RemediationStatus,
)

_metadata = sa.MetaData()
_plans = sa.Table(
    "remediation_plans",
    _metadata,
    sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
    sa.Column("incident_id", sa.Uuid(as_uuid=True), nullable=False),
    sa.Column("investigation_id", sa.Uuid(as_uuid=True), nullable=False),
    sa.Column("proposed_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("status", sa.String(32), nullable=False),
    sa.Column("risk_level", sa.Integer(), nullable=False),
    sa.Column("snapshot", sa.JSON(), nullable=False),
)
_actions = sa.Table(
    "remediation_actions",
    _metadata,
    sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
    sa.Column("plan_id", sa.Uuid(as_uuid=True), nullable=False),
    sa.Column("incident_id", sa.Uuid(as_uuid=True), nullable=False),
    sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("status", sa.String(32), nullable=False),
    sa.Column("snapshot", sa.JSON(), nullable=False),
)


class RemediationRepository:
    def __init__(self, database: Database) -> None:
        self._database = database

    async def create(self, plan: RemediationPlan) -> RemediationPlan:
        async with self._database.session() as session:
            await session.execute(
                sa.insert(_plans).values(
                    id=plan.id,
                    incident_id=plan.incident_id,
                    investigation_id=plan.investigation_id,
                    proposed_at=plan.proposed_at,
                    status=plan.status.value,
                    risk_level=int(plan.risk_level),
                    snapshot=plan.model_dump(mode="json"),
                )
            )
            await session.commit()
        return plan

    async def update(self, plan: RemediationPlan) -> RemediationPlan:
        async with self._database.session() as session:
            await session.execute(
                sa.update(_plans)
                .where(_plans.c.id == plan.id)
                .values(status=plan.status.value, snapshot=plan.model_dump(mode="json"))
            )
            await session.commit()
        return plan

    async def transition(self, plan: RemediationPlan, *, expected: RemediationStatus) -> bool:
        """Atomically claim a state transition so an action cannot execute twice."""

        statement = (
            sa.update(_plans)
            .where(_plans.c.id == plan.id, _plans.c.status == expected.value)
            .values(status=plan.status.value, snapshot=plan.model_dump(mode="json"))
            .returning(_plans.c.id)
        )
        async with self._database.session() as session:
            transitioned = (await session.execute(statement)).scalar_one_or_none()
            await session.commit()
        return transitioned is not None

    async def get(self, plan_id: UUID) -> RemediationPlan | None:
        statement = sa.select(_plans.c.snapshot).where(_plans.c.id == plan_id)
        async with self._database.session() as session:
            payload = (await session.execute(statement)).scalar_one_or_none()
        return RemediationPlan.model_validate(payload) if payload is not None else None

    async def latest(self, incident_id: UUID) -> RemediationPlan | None:
        statement = (
            sa.select(_plans.c.snapshot)
            .where(_plans.c.incident_id == incident_id)
            .order_by(_plans.c.proposed_at.desc())
            .limit(1)
        )
        async with self._database.session() as session:
            payload = (await session.execute(statement)).scalar_one_or_none()
        return RemediationPlan.model_validate(payload) if payload is not None else None

    async def save_action(self, action: RemediationAction) -> None:
        async with self._database.session() as session:
            await session.execute(
                sa.insert(_actions).values(
                    id=action.id,
                    plan_id=action.plan_id,
                    incident_id=action.incident_id,
                    started_at=action.started_at,
                    status=action.status,
                    snapshot=action.model_dump(mode="json"),
                )
            )
            await session.commit()

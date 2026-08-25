"""Add remediation plans and immutable action receipts.

Revision ID: 20260825_0006
Revises: 20260825_0005
Create Date: 2026-08-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260825_0006"
down_revision: str | None = "20260825_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "remediation_plans",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("incident_id", sa.Uuid(), sa.ForeignKey("incidents.id"), nullable=False),
        sa.Column(
            "investigation_id", sa.Uuid(), sa.ForeignKey("investigations.id"), nullable=False
        ),
        sa.Column("proposed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("risk_level", sa.Integer(), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.CheckConstraint("risk_level BETWEEN 0 AND 3", name="ck_remediation_risk_level"),
    )
    op.create_index(
        "ix_remediation_plans_incident",
        "remediation_plans",
        ["incident_id", sa.text("proposed_at DESC")],
    )
    op.create_table(
        "remediation_actions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("plan_id", sa.Uuid(), sa.ForeignKey("remediation_plans.id"), nullable=False),
        sa.Column("incident_id", sa.Uuid(), sa.ForeignKey("incidents.id"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("remediation_actions")
    op.drop_index("ix_remediation_plans_incident", table_name="remediation_plans")
    op.drop_table("remediation_plans")

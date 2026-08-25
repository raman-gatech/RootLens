"""Persist alert intake events separately from incidents.

Revision ID: 20260825_0008
Revises: 20260825_0007
Create Date: 2026-08-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260825_0008"
down_revision: str | None = "20260825_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "alerts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("incident_id", sa.Uuid(), sa.ForeignKey("incidents.id"), nullable=False),
        sa.Column("source", sa.String(80), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
    )
    op.create_index(
        "ix_alerts_incident_received",
        "alerts",
        ["incident_id", sa.text("received_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("ix_alerts_incident_received", table_name="alerts")
    op.drop_table("alerts")

"""Add pgvector-backed historical incident memory.

Revision ID: 20260825_0005
Revises: 20260825_0004
Create Date: 2026-08-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260825_0005"
down_revision: str | None = "20260825_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


class Vector(sa.types.UserDefinedType[object]):
    cache_ok = True

    def get_col_spec(self, **_: object) -> str:
        return "VECTOR(128)"


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "historical_incidents",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("source_incident_id", sa.Uuid(), sa.ForeignKey("incidents.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("root_cause_service", sa.String(160), nullable=False),
        sa.Column("failure_mode", sa.String(240), nullable=False),
        sa.Column("embedding", Vector(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
    )
    op.create_index(
        "ix_historical_incidents_created_at",
        "historical_incidents",
        [sa.text("created_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("ix_historical_incidents_created_at", table_name="historical_incidents")
    op.drop_table("historical_incidents")

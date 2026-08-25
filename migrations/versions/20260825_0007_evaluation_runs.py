"""Add aggregate evaluation reports.

Revision ID: 20260825_0007
Revises: 20260825_0006
Create Date: 2026-08-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260825_0007"
down_revision: str | None = "20260825_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "evaluation_runs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("dataset_version", sa.String(120), nullable=False),
        sa.Column("execution_mode", sa.String(40), nullable=False),
        sa.Column("incident_count", sa.Integer(), nullable=False),
        sa.Column("report", sa.JSON(), nullable=False),
        sa.CheckConstraint("incident_count > 0", name="ck_evaluation_incident_count"),
    )
    op.create_index(
        "ix_evaluation_runs_generated_at",
        "evaluation_runs",
        [sa.text("generated_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("ix_evaluation_runs_generated_at", table_name="evaluation_runs")
    op.drop_table("evaluation_runs")

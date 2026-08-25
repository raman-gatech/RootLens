"""Persist ranked telemetry anomaly snapshots.

Revision ID: 20260825_0003
Revises: 20260824_0002
Create Date: 2026-08-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260825_0003"
down_revision: str | None = "20260824_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "telemetry_anomalies",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("baseline_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("baseline_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("incident_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("incident_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("evaluated_series", sa.Integer(), nullable=False),
        sa.Column("anomaly_count", sa.Integer(), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.CheckConstraint("baseline_start < baseline_end", name="ck_anomaly_baseline_order"),
        sa.CheckConstraint("incident_start < incident_end", name="ck_anomaly_incident_order"),
        sa.CheckConstraint("baseline_end <= incident_start", name="ck_anomaly_windows_nonoverlap"),
        sa.CheckConstraint("evaluated_series >= 0", name="ck_anomaly_series_nonnegative"),
        sa.CheckConstraint("anomaly_count >= 0", name="ck_anomaly_count_nonnegative"),
    )
    op.create_index(
        "ix_telemetry_anomalies_generated_at",
        "telemetry_anomalies",
        [sa.text("generated_at DESC")],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_telemetry_anomalies_generated_at",
        table_name="telemetry_anomalies",
    )
    op.drop_table("telemetry_anomalies")

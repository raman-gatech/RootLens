"""Create evidence-grounded incident investigation records.

Revision ID: 20260825_0004
Revises: 20260825_0003
Create Date: 2026-08-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260825_0004"
down_revision: str | None = "20260825_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "incidents",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("affected_service", sa.String(160)),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.CheckConstraint("window_start < window_end", name="ck_incident_window_order"),
    )
    op.create_index("ix_incidents_created_at", "incidents", [sa.text("created_at DESC")])
    op.create_table(
        "investigations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("incident_id", sa.Uuid(), sa.ForeignKey("incidents.id"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("mode", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("provider", sa.String(80), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
    )
    op.create_index(
        "ix_investigations_incident_started",
        "investigations",
        ["incident_id", sa.text("started_at DESC")],
    )
    op.create_table(
        "evidence",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("incident_id", sa.Uuid(), sa.ForeignKey("incidents.id"), nullable=False),
        sa.Column(
            "investigation_id", sa.Uuid(), sa.ForeignKey("investigations.id"), nullable=False
        ),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("origin", sa.String(32), nullable=False),
        sa.Column("service", sa.String(160)),
        sa.Column("query_reference", sa.String(1_000), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
    )
    op.create_index("ix_evidence_incident", "evidence", ["incident_id"])
    op.create_table(
        "hypotheses",
        sa.Column(
            "investigation_id", sa.Uuid(), sa.ForeignKey("investigations.id"), primary_key=True
        ),
        sa.Column("hypothesis_id", sa.String(160), primary_key=True),
        sa.Column("incident_id", sa.Uuid(), sa.ForeignKey("incidents.id"), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.CheckConstraint("rank > 0", name="ck_hypothesis_rank_positive"),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_hypothesis_confidence"),
    )
    op.create_table(
        "agent_runs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "investigation_id", sa.Uuid(), sa.ForeignKey("investigations.id"), nullable=False
        ),
        sa.Column("incident_id", sa.Uuid(), sa.ForeignKey("incidents.id"), nullable=False),
        sa.Column("agent_id", sa.String(64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
    )
    op.create_table(
        "tool_calls",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "investigation_id", sa.Uuid(), sa.ForeignKey("investigations.id"), nullable=False
        ),
        sa.Column("incident_id", sa.Uuid(), sa.ForeignKey("incidents.id"), nullable=False),
        sa.Column("agent_id", sa.String(64), nullable=False),
        sa.Column("tool_name", sa.String(120), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
    )
    op.create_index("ix_tool_calls_investigation", "tool_calls", ["investigation_id"])


def downgrade() -> None:
    op.drop_index("ix_tool_calls_investigation", table_name="tool_calls")
    op.drop_table("tool_calls")
    op.drop_table("agent_runs")
    op.drop_table("hypotheses")
    op.drop_index("ix_evidence_incident", table_name="evidence")
    op.drop_table("evidence")
    op.drop_index("ix_investigations_incident_started", table_name="investigations")
    op.drop_table("investigations")
    op.drop_index("ix_incidents_created_at", table_name="incidents")
    op.drop_table("incidents")

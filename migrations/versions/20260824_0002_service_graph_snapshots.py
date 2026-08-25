"""Persist trace-derived service graph snapshots.

Revision ID: 20260824_0002
Revises: 20260824_0001
Create Date: 2026-08-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260824_0002"
down_revision: str | None = "20260824_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "service_graph_snapshots",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("trace_count", sa.Integer(), nullable=False),
        sa.Column("node_count", sa.Integer(), nullable=False),
        sa.Column("edge_count", sa.Integer(), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.CheckConstraint("window_start < window_end", name="ck_graph_window_order"),
        sa.CheckConstraint("trace_count >= 0", name="ck_graph_trace_count_nonnegative"),
        sa.CheckConstraint("node_count >= 0", name="ck_graph_node_count_nonnegative"),
        sa.CheckConstraint("edge_count >= 0", name="ck_graph_edge_count_nonnegative"),
    )
    op.create_index(
        "ix_service_graph_snapshots_generated_at",
        "service_graph_snapshots",
        [sa.text("generated_at DESC")],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_service_graph_snapshots_generated_at",
        table_name="service_graph_snapshots",
    )
    op.drop_table("service_graph_snapshots")

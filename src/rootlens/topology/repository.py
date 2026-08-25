"""PostgreSQL persistence for reproducible service-graph snapshots."""

import sqlalchemy as sa

from rootlens.db.session import Database
from rootlens.topology.contracts import ServiceGraphSnapshot

_metadata = sa.MetaData()
_snapshots = sa.Table(
    "service_graph_snapshots",
    _metadata,
    sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
    sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
    sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
    sa.Column("trace_count", sa.Integer(), nullable=False),
    sa.Column("node_count", sa.Integer(), nullable=False),
    sa.Column("edge_count", sa.Integer(), nullable=False),
    sa.Column("snapshot", sa.JSON(), nullable=False),
)


class ServiceGraphRepository:
    def __init__(self, database: Database) -> None:
        self._database = database

    async def save(self, snapshot: ServiceGraphSnapshot) -> None:
        statement = sa.insert(_snapshots).values(
            id=snapshot.id,
            generated_at=snapshot.generated_at,
            window_start=snapshot.window.start,
            window_end=snapshot.window.end,
            trace_count=snapshot.trace_count,
            node_count=len(snapshot.nodes),
            edge_count=len(snapshot.edges),
            snapshot=snapshot.model_dump(mode="json"),
        )
        async with self._database.session() as session:
            await session.execute(statement)
            await session.commit()

    async def latest(self) -> ServiceGraphSnapshot | None:
        statement = (
            sa.select(_snapshots.c.snapshot).order_by(_snapshots.c.generated_at.desc()).limit(1)
        )
        async with self._database.session() as session:
            result = await session.execute(statement)
            payload = result.scalar_one_or_none()
        if payload is None:
            return None
        return ServiceGraphSnapshot.model_validate(payload)

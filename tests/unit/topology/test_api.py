"""Topology HTTP contract tests."""

from datetime import UTC, datetime, timedelta
from typing import cast

from httpx import ASGITransport, AsyncClient

from rootlens.api.topology import get_topology_service
from rootlens.config import Settings
from rootlens.main import create_app
from rootlens.telemetry import QueryWindow
from rootlens.topology.contracts import ServiceEdge, ServiceGraphSnapshot, ServiceNode
from rootlens.topology.service import ServiceTopologyService


class FakeTopologyService:
    def __init__(self, graph_snapshot: ServiceGraphSnapshot) -> None:
        self.snapshot = graph_snapshot

    async def latest(self) -> ServiceGraphSnapshot:
        return self.snapshot


async def test_latest_topology_and_dependency_path_are_exposed() -> None:
    now = datetime(2026, 8, 24, 12, tzinfo=UTC)
    snapshot = ServiceGraphSnapshot(
        window=QueryWindow(start=now, end=now + timedelta(minutes=1)),
        trace_count=1,
        nodes=(node("frontend"), node("checkout")),
        edges=(edge("frontend", "checkout", now),),
        evidence_references=("telemetry://tempo/test",),
    )
    app = create_app(Settings(telemetry_enabled=False))
    fake = cast(ServiceTopologyService, FakeTopologyService(snapshot))
    app.dependency_overrides[get_topology_service] = lambda: fake

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        latest = await client.get("/api/v1/topology/latest")
        path = await client.get(
            "/api/v1/topology/latest/path",
            params={"source": "frontend", "target": "checkout"},
        )
    await app.state.database.close()
    await app.state.telemetry_gateway.aclose()

    assert latest.status_code == 200
    assert latest.json()["trace_count"] == 1
    assert path.status_code == 200
    assert path.json()["services"] == ["frontend", "checkout"]


def node(service: str) -> ServiceNode:
    return ServiceNode(
        service=service,
        span_count=1,
        trace_count=1,
        error_count=0,
        error_rate=0,
    )


def edge(caller: str, callee: str, now: datetime) -> ServiceEdge:
    return ServiceEdge(
        caller=caller,
        callee=callee,
        request_count=1,
        trace_count=1,
        failure_count=0,
        error_rate=0,
        request_rate_per_second=1,
        p50_latency_ms=1,
        p95_latency_ms=1,
        p99_latency_ms=1,
        first_seen=now,
        last_seen=now + timedelta(milliseconds=1),
    )

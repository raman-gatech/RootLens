"""Service dependency traversal tests."""

from datetime import UTC, datetime, timedelta

import pytest

from rootlens.telemetry import QueryWindow
from rootlens.topology import ServiceEdge, ServiceGraph, ServiceGraphSnapshot, ServiceNode
from rootlens.topology.errors import ServiceNotFoundError, ServicePathNotFoundError


def test_dependency_and_reverse_impact_traversal() -> None:
    graph = ServiceGraph(snapshot())

    assert graph.direct_dependencies("checkout").services == ("cart", "payment")
    assert graph.dependencies("frontend").services == ("cart", "checkout", "payment")
    assert graph.callers("payment").services == ("checkout", "frontend")
    assert graph.shortest_dependency_path("frontend", "payment").services == (
        "frontend",
        "checkout",
        "payment",
    )


def test_traversal_fails_explicitly_for_unknown_or_disconnected_services() -> None:
    graph = ServiceGraph(snapshot())

    with pytest.raises(ServiceNotFoundError):
        graph.dependencies("unknown")
    with pytest.raises(ServicePathNotFoundError):
        graph.shortest_dependency_path("payment", "frontend")


def snapshot() -> ServiceGraphSnapshot:
    now = datetime(2026, 8, 24, 12, tzinfo=UTC)
    services = ("frontend", "checkout", "cart", "payment")
    return ServiceGraphSnapshot(
        window=QueryWindow(start=now, end=now + timedelta(minutes=1)),
        trace_count=1,
        nodes=tuple(
            ServiceNode(
                service=service,
                span_count=1,
                trace_count=1,
                error_count=0,
                error_rate=0,
            )
            for service in services
        ),
        edges=(
            edge("frontend", "checkout", now),
            edge("checkout", "cart", now),
            edge("checkout", "payment", now),
        ),
        evidence_references=("telemetry://tempo/test",),
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

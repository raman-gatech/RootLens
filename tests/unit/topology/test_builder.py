"""Deterministic trace-to-service-graph tests."""

from datetime import UTC, datetime, timedelta

import pytest

from rootlens.telemetry import QueryWindow
from rootlens.telemetry.contracts import SpanRecord
from rootlens.topology import ServiceGraphBuilder


def span(
    *,
    trace_id: str,
    span_id: str,
    service: str,
    start: datetime,
    duration_ms: int,
    parent_id: str | None = None,
    status: str | None = None,
) -> SpanRecord:
    return SpanRecord(
        trace_id=trace_id,
        span_id=span_id,
        parent_span_id=parent_id,
        service_name=service,
        name=f"{service} operation",
        start_time=start,
        end_time=start + timedelta(milliseconds=duration_ms),
        status_code=status,
    )


def test_builds_cross_service_edges_and_aggregates_latency() -> None:
    start = datetime(2026, 8, 24, 12, tzinfo=UTC)
    window = QueryWindow(start=start, end=start + timedelta(seconds=10))
    spans = [
        span(trace_id="trace-1", span_id="front", service="frontend", start=start, duration_ms=100),
        span(
            trace_id="trace-1",
            span_id="checkout",
            parent_id="front",
            service="checkout",
            start=start,
            duration_ms=50,
        ),
        span(
            trace_id="trace-1",
            span_id="payment",
            parent_id="checkout",
            service="payment",
            start=start,
            duration_ms=30,
            status="STATUS_CODE_ERROR",
        ),
        span(
            trace_id="trace-2",
            span_id="checkout-2",
            service="checkout",
            start=start + timedelta(seconds=1),
            duration_ms=20,
        ),
        span(
            trace_id="trace-2",
            span_id="payment-2",
            parent_id="checkout-2",
            service="payment",
            start=start + timedelta(seconds=1),
            duration_ms=10,
        ),
        span(
            trace_id="trace-2",
            span_id="payment-internal",
            parent_id="payment-2",
            service="payment",
            start=start + timedelta(seconds=1),
            duration_ms=5,
        ),
    ]

    snapshot = ServiceGraphBuilder().build(
        spans,
        window=window,
        evidence_references=["telemetry://tempo/search", "telemetry://tempo/trace-1"],
    )

    assert snapshot.trace_count == 2
    assert [node.service for node in snapshot.nodes] == ["checkout", "frontend", "payment"]
    assert [(edge.caller, edge.callee) for edge in snapshot.edges] == [
        ("checkout", "payment"),
        ("frontend", "checkout"),
    ]
    payment_edge = snapshot.edges[0]
    assert payment_edge.request_count == 2
    assert payment_edge.trace_count == 2
    assert payment_edge.failure_count == 1
    assert payment_edge.error_rate == 0.5
    assert payment_edge.request_rate_per_second == 0.2
    assert payment_edge.p50_latency_ms == pytest.approx(20)
    assert payment_edge.p95_latency_ms == pytest.approx(29)
    assert payment_edge.p99_latency_ms == pytest.approx(29.8)


def test_graph_build_is_deterministically_sorted() -> None:
    start = datetime(2026, 8, 24, 12, tzinfo=UTC)
    snapshot = ServiceGraphBuilder().build(
        [
            span(trace_id="t", span_id="b", service="z-service", start=start, duration_ms=1),
            span(trace_id="t", span_id="a", service="a-service", start=start, duration_ms=1),
        ],
        window=QueryWindow(start=start, end=start + timedelta(seconds=1)),
        evidence_references=["b", "a", "a"],
    )

    assert [node.service for node in snapshot.nodes] == ["a-service", "z-service"]
    assert snapshot.evidence_references == ("a", "b")

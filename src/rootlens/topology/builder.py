"""Deterministic reconstruction of service dependencies from OTLP spans."""

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime

from rootlens.telemetry import QueryWindow
from rootlens.telemetry.contracts import SpanRecord
from rootlens.topology.contracts import ServiceEdge, ServiceGraphSnapshot, ServiceNode


@dataclass
class _NodeAccumulator:
    spans: int = 0
    errors: int = 0
    traces: set[str] = field(default_factory=set)


@dataclass
class _EdgeAccumulator:
    requests: int = 0
    failures: int = 0
    traces: set[str] = field(default_factory=set)
    latencies_ms: list[float] = field(default_factory=list)
    first_seen: datetime | None = None
    last_seen: datetime | None = None


class ServiceGraphBuilder:
    """Build caller-to-callee edges only from cross-service parent spans."""

    def build(
        self,
        spans: Sequence[SpanRecord],
        *,
        window: QueryWindow,
        evidence_references: Sequence[str],
        warnings: Sequence[str] = (),
    ) -> ServiceGraphSnapshot:
        nodes: defaultdict[str, _NodeAccumulator] = defaultdict(_NodeAccumulator)
        edges: defaultdict[tuple[str, str], _EdgeAccumulator] = defaultdict(_EdgeAccumulator)
        spans_by_id = {(span.trace_id, span.span_id): span for span in spans}

        for span in spans:
            if span.service_name is None:
                continue
            node = nodes[span.service_name]
            node.spans += 1
            node.traces.add(span.trace_id)
            if _is_error(span.status_code):
                node.errors += 1

            if span.parent_span_id is None:
                continue
            parent = spans_by_id.get((span.trace_id, span.parent_span_id))
            if (
                parent is None
                or parent.service_name is None
                or parent.service_name == span.service_name
            ):
                continue

            edge = edges[(parent.service_name, span.service_name)]
            edge.requests += 1
            edge.traces.add(span.trace_id)
            edge.latencies_ms.append(
                max((span.end_time - span.start_time).total_seconds(), 0) * 1_000
            )
            if _is_error(span.status_code):
                edge.failures += 1
            edge.first_seen = (
                span.start_time
                if edge.first_seen is None
                else min(edge.first_seen, span.start_time)
            )
            edge.last_seen = (
                span.end_time if edge.last_seen is None else max(edge.last_seen, span.end_time)
            )

        duration_seconds = (window.end - window.start).total_seconds()
        normalized_nodes = tuple(
            ServiceNode(
                service=service,
                span_count=value.spans,
                trace_count=len(value.traces),
                error_count=value.errors,
                error_rate=value.errors / value.spans if value.spans else 0,
            )
            for service, value in sorted(nodes.items())
        )
        normalized_edges = tuple(
            _normalize_edge(caller, callee, value, duration_seconds)
            for (caller, callee), value in sorted(edges.items())
        )
        return ServiceGraphSnapshot(
            window=window,
            trace_count=len({span.trace_id for span in spans}),
            nodes=normalized_nodes,
            edges=normalized_edges,
            evidence_references=tuple(sorted(set(evidence_references))),
            warnings=tuple(warnings),
        )


def _normalize_edge(
    caller: str,
    callee: str,
    value: _EdgeAccumulator,
    window_seconds: float,
) -> ServiceEdge:
    latencies = sorted(value.latencies_ms)
    if value.first_seen is None or value.last_seen is None:
        raise AssertionError("an observed edge must have timestamps")
    return ServiceEdge(
        caller=caller,
        callee=callee,
        request_count=value.requests,
        trace_count=len(value.traces),
        failure_count=value.failures,
        error_rate=value.failures / value.requests,
        request_rate_per_second=value.requests / window_seconds,
        p50_latency_ms=_percentile(latencies, 0.50),
        p95_latency_ms=_percentile(latencies, 0.95),
        p99_latency_ms=_percentile(latencies, 0.99),
        first_seen=value.first_seen,
        last_seen=value.last_seen,
    )


def _percentile(sorted_values: Sequence[float], quantile: float) -> float:
    if not sorted_values:
        return 0
    position = (len(sorted_values) - 1) * quantile
    lower_index = int(position)
    upper_index = min(lower_index + 1, len(sorted_values) - 1)
    fraction = position - lower_index
    return (
        sorted_values[lower_index]
        + (sorted_values[upper_index] - sorted_values[lower_index]) * fraction
    )


def _is_error(status_code: str | None) -> bool:
    return status_code is not None and status_code.upper().endswith("ERROR")

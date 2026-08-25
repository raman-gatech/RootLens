"""Deterministic causal ranking tests."""

from datetime import UTC, datetime, timedelta

from rootlens.investigation.causal import CausalRanker
from rootlens.investigation.contracts import (
    AgentRole,
    Evidence,
    EvidenceSource,
    Hypothesis,
    HypothesisStatus,
    Incident,
)
from rootlens.telemetry import QueryWindow
from rootlens.topology import ServiceEdge, ServiceGraphSnapshot, ServiceNode


def test_causal_rank_prefers_early_anomalous_critical_dependency() -> None:
    start = datetime(2026, 8, 25, 12, tzinfo=UTC)
    window = QueryWindow(start=start, end=start + timedelta(minutes=5))
    incident = Incident(title="Frontend slow", affected_service="frontend", window=window)
    checkout = _evidence("checkout", start + timedelta(seconds=10), 0.95)
    ad = _evidence("ad", start + timedelta(minutes=4), 0.55)
    graph = ServiceGraphSnapshot(
        window=window,
        trace_count=10,
        nodes=(_node("frontend"), _node("checkout"), _node("payment"), _node("ad")),
        edges=(
            _edge("frontend", "checkout", start, 100),
            _edge("checkout", "payment", start, 80),
            _edge("frontend", "ad", start, 5),
        ),
        evidence_references=("telemetry://tempo/test",),
    )
    hypotheses = (_hypothesis("ad", ad), _hypothesis("checkout", checkout))

    ranked = CausalRanker().rank(hypotheses, (checkout, ad), incident, graph)

    assert ranked[0].root_cause_service == "checkout"
    assert ranked[0].causal_score.anomaly_strength == 0.95
    assert ranked[0].causal_score.temporal_precedence > ranked[1].causal_score.temporal_precedence


def _evidence(service: str, observed_at: datetime, score: float) -> Evidence:
    return Evidence(
        source=EvidenceSource.METRICS,
        service=service,
        signal="p95_latency",
        observation="latency anomaly",
        query_reference="telemetry://prometheus/test",
        confidence=score,
        observed_at=observed_at,
        attributes={"anomaly_score": score},
    )


def _hypothesis(service: str, evidence: Evidence) -> Hypothesis:
    return Hypothesis(
        id=f"service:{service}",
        rank=1,
        root_cause_service=service,
        component=service,
        failure_mode="latency regression",
        description="candidate",
        evidence_for=(evidence.id,),
        confidence=evidence.confidence,
        status=HypothesisStatus.SUPPORTED,
        generated_by=AgentRole.MANAGER,
    )


def _node(service: str) -> ServiceNode:
    return ServiceNode(service=service, span_count=10, trace_count=10, error_count=0, error_rate=0)


def _edge(caller: str, callee: str, now: datetime, requests: int) -> ServiceEdge:
    return ServiceEdge(
        caller=caller,
        callee=callee,
        request_count=requests,
        trace_count=10,
        failure_count=0,
        error_rate=0,
        request_rate_per_second=1,
        p50_latency_ms=10,
        p95_latency_ms=20,
        p99_latency_ms=30,
        first_seen=now,
        last_seen=now + timedelta(minutes=1),
    )

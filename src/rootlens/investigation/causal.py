"""Deterministic graph- and time-grounded causal hypothesis ranking."""

from __future__ import annotations

from collections import defaultdict

import networkx as nx

from rootlens.investigation.contracts import (
    CausalScore,
    Evidence,
    EvidenceOrigin,
    EvidenceSource,
    Hypothesis,
    HypothesisStatus,
    Incident,
)
from rootlens.topology import ServiceGraphSnapshot


class CausalRanker:
    """Apply the published RootLens weights without model-dependent arithmetic."""

    def rank(
        self,
        hypotheses: tuple[Hypothesis, ...],
        evidence: tuple[Evidence, ...],
        incident: Incident,
        graph: ServiceGraphSnapshot | None,
    ) -> tuple[Hypothesis, ...]:
        evidence_by_id = {item.id: item for item in evidence}
        graph_scores = _graph_scores(graph, incident.affected_service)
        scored: list[tuple[float, Hypothesis, CausalScore]] = []
        for hypothesis in hypotheses:
            supporting = [
                evidence_by_id[item]
                for item in hypothesis.evidence_for
                if item in evidence_by_id and evidence_by_id[item].origin is EvidenceOrigin.CURRENT
            ]
            opposing = [
                evidence_by_id[item]
                for item in hypothesis.evidence_against
                if item in evidence_by_id
            ]
            by_source: dict[EvidenceSource, list[Evidence]] = defaultdict(list)
            for item in supporting:
                by_source[item.source].append(item)

            anomaly = _maximum(by_source[EvidenceSource.METRICS], "anomaly_score")
            temporal = _temporal_precedence(supporting, incident)
            criticality, consistency = graph_scores.get(hypothesis.root_cause_service, (0.0, 0.0))
            log_score = _confidence(by_source[EvidenceSource.LOGS])
            change_score = max(
                _confidence(by_source[EvidenceSource.CHANGES]),
                _confidence(by_source[EvidenceSource.KUBERNETES]),
            )
            memory_items = [
                item
                for item in evidence
                if item.source is EvidenceSource.MEMORY
                and item.service == hypothesis.root_cause_service
            ]
            memory_score = _maximum(memory_items, "similarity")
            contradiction = _confidence(opposing)
            raw = (
                0.25 * anomaly
                + 0.20 * temporal
                + 0.20 * criticality
                + 0.15 * consistency
                + 0.10 * log_score
                + 0.05 * change_score
                + 0.05 * memory_score
            )
            total = max(0.0, min(1.0, raw * (1 - 0.5 * contradiction)))
            causal = CausalScore(
                anomaly_strength=anomaly,
                temporal_precedence=temporal,
                trace_criticality=criticality,
                graph_consistency=consistency,
                log_evidence=log_score,
                recent_change=change_score,
                historical_similarity=memory_score,
                contradiction_penalty=contradiction,
                total=total,
            )
            combined = min(1.0, 0.7 * total + 0.3 * hypothesis.confidence)
            scored.append((combined, hypothesis, causal))

        scored.sort(key=lambda row: (-row[0], row[1].root_cause_service, row[1].id))
        result: list[Hypothesis] = []
        for rank, (confidence, hypothesis, causal) in enumerate(scored, start=1):
            status = hypothesis.status
            if not hypothesis.evidence_for:
                status = HypothesisStatus.WEAK
            elif confidence >= 0.45 and status is not HypothesisStatus.REJECTED:
                status = HypothesisStatus.SUPPORTED
            elif status is not HypothesisStatus.REJECTED:
                status = HypothesisStatus.WEAK
            result.append(
                hypothesis.model_copy(
                    update={
                        "rank": rank,
                        "confidence": round(confidence, 6),
                        "status": status,
                        "causal_score": causal,
                    }
                )
            )
        return tuple(result)


def _confidence(items: list[Evidence]) -> float:
    return max((item.confidence for item in items), default=0.0)


def _maximum(items: list[Evidence], attribute: str) -> float:
    values = [item.attributes.get(attribute, item.confidence) for item in items]
    numeric = [float(value) for value in values if isinstance(value, int | float)]
    return max((min(1.0, max(0.0, item)) for item in numeric), default=0.0)


def _temporal_precedence(items: list[Evidence], incident: Incident) -> float:
    if not items:
        return 0.0
    duration = max(1.0, (incident.window.end - incident.window.start).total_seconds())
    scores = []
    for item in items:
        offset = (item.observed_at - incident.window.start).total_seconds()
        scores.append(max(0.0, min(1.0, 1.0 - max(0.0, offset) / duration)))
    return max(scores)


def _graph_scores(
    snapshot: ServiceGraphSnapshot | None, affected_service: str | None
) -> dict[str, tuple[float, float]]:
    if snapshot is None or not snapshot.nodes:
        return {}
    graph: nx.DiGraph[str] = nx.DiGraph()
    request_counts: dict[str, int] = defaultdict(int)
    for node in snapshot.nodes:
        graph.add_node(node.service)
    for edge in snapshot.edges:
        graph.add_edge(edge.caller, edge.callee)
        request_counts[edge.callee] += edge.request_count
    max_degree = max((graph.degree(node) for node in graph.nodes), default=1)
    max_requests = max(request_counts.values(), default=1)
    scores: dict[str, tuple[float, float]] = {}
    for service in graph.nodes:
        degree_score = graph.degree(service) / max_degree if max_degree else 0.0
        traffic_score = request_counts[service] / max_requests if max_requests else 0.0
        criticality = min(1.0, 0.5 * degree_score + 0.5 * traffic_score)
        if affected_service is None or affected_service not in graph:
            consistency = degree_score
        elif service == affected_service:
            consistency = 1.0
        elif nx.has_path(graph, affected_service, service):
            distance = nx.shortest_path_length(graph, affected_service, service)
            consistency = 1 / (1 + distance)
        elif nx.has_path(graph, service, affected_service):
            distance = nx.shortest_path_length(graph, service, affected_service)
            consistency = 0.8 / (1 + distance)
        else:
            consistency = 0.0
        scores[service] = (criticality, consistency)
    return scores

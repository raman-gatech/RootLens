"""Allowlisted, audited evidence tools used by investigation agents."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from uuid import UUID

from rootlens.anomaly import SignalName
from rootlens.anomaly.service import AnomalyAnalysisService
from rootlens.investigation.contracts import (
    AgentRole,
    Evidence,
    EvidenceBundle,
    EvidenceSource,
    Incident,
    ToolCallAudit,
)
from rootlens.telemetry import QueryWindow, TelemetryGateway
from rootlens.topology import ServiceGraphSnapshot
from rootlens.topology.service import ServiceTopologyService

_ERROR_PATTERN = re.compile(
    r"\b(error|exception|failed|failure|timeout|unavailable|refused|panic|fatal)\b",
    re.IGNORECASE,
)


class EvidenceToolbox:
    """A fixed read-only tool surface; arbitrary commands and queries are impossible."""

    def __init__(
        self,
        *,
        gateway: TelemetryGateway,
        anomaly_service: AnomalyAnalysisService,
        topology_service: ServiceTopologyService,
        namespace: str,
        log_limit: int = 500,
    ) -> None:
        self._gateway = gateway
        self._anomaly_service = anomaly_service
        self._topology_service = topology_service
        self._namespace = namespace
        self._log_limit = log_limit

    async def metrics(
        self, incident: Incident, investigation_id: UUID, agent: AgentRole
    ) -> EvidenceBundle:
        started = datetime.now(UTC)
        baseline = _baseline_window(incident.window)
        arguments = {
            "baseline_start": baseline.start.isoformat(),
            "baseline_end": baseline.end.isoformat(),
            "incident_start": incident.window.start.isoformat(),
            "incident_end": incident.window.end.isoformat(),
            "signals": [item.value for item in SignalName],
        }
        try:
            duration = (incident.window.end - incident.window.start).total_seconds()
            step = max(10, min(60, int(duration / 20)))
            snapshot = await self._anomaly_service.analyze(
                baseline_window=baseline,
                incident_window=incident.window,
                signals=tuple(SignalName),
                step_seconds=step,
                minimum_score=0.35,
            )
            evidence = tuple(
                Evidence(
                    source=EvidenceSource.METRICS,
                    service=item.service,
                    signal=item.signal.value,
                    observation=(
                        f"{item.signal.value} moved {item.direction.value}; anomaly score "
                        f"{item.score:.3f}, peak {item.peak_value:.3f}."
                    ),
                    window=incident.window,
                    supports=(f"service:{item.service}",),
                    query_reference=item.evidence_references[-1],
                    confidence=item.score,
                    observed_at=item.anomaly_start_time,
                    attributes={
                        "anomaly_score": item.score,
                        "direction": item.direction.value,
                        "peak_value": item.peak_value,
                        "anomaly_start_time": item.anomaly_start_time.isoformat(),
                        "rank": item.rank,
                    },
                )
                for item in snapshot.anomalies[:20]
            )
            return _success_bundle(
                incident, investigation_id, agent, "analyze_metrics", arguments, started, evidence
            )
        except Exception as error:  # tool failures are isolated and made visible
            return _error_bundle(
                incident, investigation_id, agent, "analyze_metrics", arguments, started, error
            )

    async def traces(
        self, incident: Incident, investigation_id: UUID, agent: AgentRole
    ) -> EvidenceBundle:
        started = datetime.now(UTC)
        arguments = {"window": incident.window.model_dump(mode="json"), "traceql": "{}"}
        try:
            graph = await self._topology_service.rebuild(incident.window)
            significant_edges = tuple(
                edge
                for edge in graph.edges
                if edge.error_rate >= 0.05 or edge.p95_latency_ms >= 500
            )
            ordered = sorted(
                significant_edges,
                key=lambda edge: (edge.error_rate, edge.p95_latency_ms, edge.request_count),
                reverse=True,
            )
            evidence = tuple(
                Evidence(
                    source=EvidenceSource.TRACES,
                    service=edge.callee,
                    signal="service_dependency",
                    observation=(
                        f"{edge.caller} -> {edge.callee}: {edge.request_count} requests, "
                        f"{edge.error_rate:.1%} errors, p95 {edge.p95_latency_ms:.1f} ms."
                    ),
                    window=incident.window,
                    supports=(f"service:{edge.callee}",),
                    query_reference=graph.evidence_references[0],
                    confidence=min(1.0, 0.35 + edge.error_rate + edge.p95_latency_ms / 5_000),
                    observed_at=edge.first_seen,
                    attributes={
                        "caller": edge.caller,
                        "callee": edge.callee,
                        "error_rate": edge.error_rate,
                        "p95_latency_ms": edge.p95_latency_ms,
                        "request_count": edge.request_count,
                    },
                )
                for edge in ordered[:20]
            )
            return _success_bundle(
                incident,
                investigation_id,
                agent,
                "reconstruct_trace_graph",
                arguments,
                started,
                evidence,
                graph=graph,
            )
        except Exception as error:
            return _error_bundle(
                incident,
                investigation_id,
                agent,
                "reconstruct_trace_graph",
                arguments,
                started,
                error,
            )

    async def logs(
        self, incident: Incident, investigation_id: UUID, agent: AgentRole
    ) -> EvidenceBundle:
        started = datetime.now(UTC)
        logql = '{service_name=~".+"}'
        arguments = {
            "logql": logql,
            "window": incident.window.model_dump(mode="json"),
            "limit": self._log_limit,
        }
        try:
            result = await self._gateway.loki.query_range(
                logql, incident.window, limit=self._log_limit
            )
            evidence: list[Evidence] = []
            for stream in result.data:
                service = stream.labels.get("service_name") or stream.labels.get("service")
                matches = [entry for entry in stream.entries if _ERROR_PATTERN.search(entry.line)]
                if not matches:
                    continue
                categories = sorted(
                    {
                        match.group(1).lower()
                        for entry in matches
                        if (match := _ERROR_PATTERN.search(entry.line)) is not None
                    }
                )
                evidence.append(
                    Evidence(
                        source=EvidenceSource.LOGS,
                        service=service,
                        signal="error_log_pattern",
                        observation=(
                            f"Observed {len(matches)} log lines matching failure categories: "
                            f"{', '.join(categories)}. Raw log content is isolated as untrusted."
                        ),
                        window=incident.window,
                        supports=(f"service:{service}",) if service else (),
                        query_reference=result.provenance.reference,
                        confidence=min(0.9, 0.4 + len(matches) / 100),
                        observed_at=min(item.timestamp for item in matches),
                        attributes={
                            "matching_lines": len(matches),
                            "categories": categories,
                            "stream_labels": stream.labels,
                        },
                        untrusted_content=True,
                    )
                )
            return _success_bundle(
                incident,
                investigation_id,
                agent,
                "summarize_error_logs",
                arguments,
                started,
                tuple(evidence[:20]),
            )
        except Exception as error:
            return _error_bundle(
                incident,
                investigation_id,
                agent,
                "summarize_error_logs",
                arguments,
                started,
                error,
            )

    async def changes(
        self, incident: Incident, investigation_id: UUID, agent: AgentRole
    ) -> EvidenceBundle:
        started = datetime.now(UTC)
        arguments = {"namespace": self._namespace, "resource": "deployments_and_events"}
        try:
            changes = await self._gateway.kubernetes.list_change_events(self._namespace)
            deployments = await self._gateway.kubernetes.list_deployments(self._namespace)
            evidence: list[Evidence] = []
            for item in changes.data:
                if item.timestamp is None or not (
                    incident.window.start - timedelta(minutes=30)
                    <= item.timestamp
                    <= incident.window.end
                ):
                    continue
                evidence.append(
                    Evidence(
                        source=EvidenceSource.CHANGES,
                        service=item.resource_name,
                        signal=item.change_type,
                        observation=(
                            f"Kubernetes {item.resource_kind} {item.resource_name} emitted "
                            f"change event {item.change_type}."
                        ),
                        window=incident.window,
                        supports=(f"service:{item.resource_name}",),
                        query_reference=changes.provenance.reference,
                        confidence=0.55,
                        observed_at=item.timestamp,
                        attributes=item.details,
                    )
                )
            unhealthy = [
                item
                for item in deployments.data
                if item.replicas is not None and item.ready_replicas != item.replicas
            ]
            evidence.extend(
                Evidence(
                    source=EvidenceSource.KUBERNETES,
                    service=item.name,
                    signal="deployment_readiness",
                    observation=(
                        f"Deployment {item.name} has {item.ready_replicas or 0}/"
                        f"{item.replicas or 0} ready replicas."
                    ),
                    window=incident.window,
                    supports=(f"service:{item.name}",),
                    query_reference=deployments.provenance.reference,
                    confidence=0.9,
                    attributes={
                        "namespace": item.namespace,
                        "replicas": item.replicas,
                        "ready_replicas": item.ready_replicas,
                    },
                )
                for item in unhealthy
            )
            return _success_bundle(
                incident,
                investigation_id,
                agent,
                "collect_recent_changes",
                arguments,
                started,
                tuple(evidence[:20]),
            )
        except Exception as error:
            return _error_bundle(
                incident,
                investigation_id,
                agent,
                "collect_recent_changes",
                arguments,
                started,
                error,
            )


def _baseline_window(incident_window: QueryWindow) -> QueryWindow:
    duration = incident_window.end - incident_window.start
    duration = max(duration, timedelta(minutes=2))
    return QueryWindow(start=incident_window.start - duration, end=incident_window.start)


def _success_bundle(
    incident: Incident,
    investigation_id: UUID,
    agent: AgentRole,
    name: str,
    arguments: Mapping[str, object],
    started: datetime,
    evidence: tuple[Evidence, ...],
    *,
    graph: ServiceGraphSnapshot | None = None,
) -> EvidenceBundle:
    completed = datetime.now(UTC)
    result_bytes = len(
        json.dumps([item.model_dump(mode="json") for item in evidence], separators=(",", ":"))
    )
    audit = ToolCallAudit(
        incident_id=incident.id,
        investigation_id=investigation_id,
        agent_id=agent,
        tool_name=name,
        arguments=dict(arguments),
        started_at=started,
        completed_at=completed,
        status="success",
        result_bytes=result_bytes,
        evidence_ids=tuple(item.id for item in evidence),
    )
    return EvidenceBundle(agent=agent, evidence=evidence, tool_calls=(audit,), graph=graph)


def _error_bundle(
    incident: Incident,
    investigation_id: UUID,
    agent: AgentRole,
    name: str,
    arguments: Mapping[str, object],
    started: datetime,
    error: Exception,
) -> EvidenceBundle:
    message = f"{type(error).__name__}: {str(error)[:300]}"
    audit = ToolCallAudit(
        incident_id=incident.id,
        investigation_id=investigation_id,
        agent_id=agent,
        tool_name=name,
        arguments=dict(arguments),
        started_at=started,
        completed_at=datetime.now(UTC),
        status="error",
        error=message,
    )
    return EvidenceBundle(
        agent=agent,
        evidence=(),
        tool_calls=(audit,),
        warnings=(f"{name} failed: {message}",),
    )

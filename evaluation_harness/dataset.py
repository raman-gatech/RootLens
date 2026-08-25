"""Deterministic 20-fault, five-repetition evidence replay dataset."""

from __future__ import annotations

import hashlib
import random
from datetime import UTC, datetime, timedelta
from uuid import NAMESPACE_URL, uuid5

from evaluation_harness.contracts import BenchmarkCase
from experiment_controller.catalog import scenario
from experiment_controller.contracts import FaultType
from rootlens.investigation import Evidence, EvidenceOrigin, EvidenceSource, Incident
from rootlens.telemetry import QueryWindow
from rootlens.topology import ServiceEdge, ServiceGraphSnapshot, ServiceNode

_SERVICES = (
    "frontend-proxy",
    "frontend",
    "checkout",
    "cart",
    "payment",
    "product-catalog",
    "currency",
    "shipping",
    "email",
    "recommendation",
    "ad",
    "image-provider",
)
_EDGES = (
    ("frontend-proxy", "frontend"),
    ("frontend", "checkout"),
    ("frontend", "recommendation"),
    ("frontend", "ad"),
    ("frontend", "product-catalog"),
    ("checkout", "cart"),
    ("checkout", "payment"),
    ("checkout", "currency"),
    ("checkout", "shipping"),
    ("checkout", "email"),
    ("product-catalog", "image-provider"),
)


def build_dataset(*, repetitions: int = 5) -> tuple[BenchmarkCase, ...]:
    cases = [
        _case(fault_type, repetition)
        for fault_type in FaultType
        for repetition in range(1, repetitions + 1)
    ]
    return tuple(cases)


def _case(fault_type: FaultType, repetition: int) -> BenchmarkCase:
    spec = scenario(fault_type)
    case_id = f"{fault_type.value}-{repetition:02d}"
    # Deterministic benchmark generation, never a security or identity primitive.
    rng = random.Random(_seed(case_id))  # nosec B311
    start = datetime(2026, 8, 1, 12, tzinfo=UTC) + timedelta(
        hours=list(FaultType).index(fault_type), minutes=repetition * 10
    )
    window = QueryWindow(start=start, end=start + timedelta(minutes=5))
    affected = "frontend-proxy"
    cause = spec.target_service
    incident = Incident(
        id=uuid5(NAMESPACE_URL, f"rootlens-eval-incident:{case_id}"),
        title=f"Customer request degradation ({case_id})",
        summary="Synthetic blind replay assembled from normalized telemetry features.",
        affected_service=affected,
        window=window,
        labels={"dataset_case": case_id},
    )
    evidence = _evidence(case_id, fault_type, cause, affected, window, rng)
    graph = _graph(case_id, cause, window, rng)
    distractors = [service for service in _SERVICES if service not in {cause, affected}]
    rng.shuffle(distractors)
    candidates = tuple(dict.fromkeys((affected, cause, *distractors[:3])))
    return BenchmarkCase(
        case_id=case_id,
        fault_type=fault_type,
        repetition=repetition,
        root_cause_service=cause,
        incident=incident,
        evidence=evidence,
        graph=graph,
        candidates=candidates,
    )


def _evidence(
    case_id: str,
    fault_type: FaultType,
    cause: str,
    affected: str,
    window: QueryWindow,
    rng: random.Random,
) -> tuple[Evidence, ...]:
    signal = _signal(fault_type)
    cause_score = 0.68 + rng.random() * 0.27
    affected_score = 0.60 + rng.random() * 0.25
    items = [
        _item(
            case_id,
            "cause-metric",
            EvidenceSource.METRICS,
            cause,
            signal,
            f"{signal} anomaly begins at {cause}.",
            cause_score,
            window.start + timedelta(seconds=10 + rng.randint(0, 25)),
            window,
            {"anomaly_score": cause_score},
        ),
        _item(
            case_id,
            "impact-metric",
            EvidenceSource.METRICS,
            affected,
            "request_degradation",
            f"Customer-facing impact is visible at {affected}.",
            affected_score,
            window.start + timedelta(seconds=80 + rng.randint(0, 40)),
            window,
            {"anomaly_score": affected_score},
        ),
        _item(
            case_id,
            "cause-trace",
            EvidenceSource.TRACES,
            cause,
            "dependency_path",
            f"Trace critical path terminates at degraded service {cause}.",
            0.70 + rng.random() * 0.2,
            window.start + timedelta(seconds=35),
            window,
            {"error_rate": 0.25 + rng.random() * 0.5},
        ),
    ]
    if fault_type not in {FaultType.CPU_STRESS, FaultType.MEMORY_STRESS, FaultType.TIME_SKEW}:
        items.append(
            _item(
                case_id,
                "cause-log",
                EvidenceSource.LOGS,
                cause,
                "error_pattern",
                f"Failure-pattern log counts increase for {cause}; raw content remains untrusted.",
                0.62 + rng.random() * 0.2,
                window.start + timedelta(seconds=45),
                window,
                {},
            )
        )
    if fault_type in {
        FaultType.POD_KILL,
        FaultType.POD_FAILURE,
        FaultType.CONTAINER_KILL,
        FaultType.CPU_STRESS,
        FaultType.MEMORY_STRESS,
    }:
        items.append(
            _item(
                case_id,
                "kubernetes",
                EvidenceSource.KUBERNETES,
                cause,
                "workload_state",
                f"Workload state changed for {cause} during the incident window.",
                0.74,
                window.start + timedelta(seconds=20),
                window,
                {},
            )
        )
    wrong_memory = _SERVICES[_seed(case_id + ":memory") % len(_SERVICES)]
    memory_service = cause if repetition_mod(case_id, 4) else wrong_memory
    memory_similarity = 0.72 + rng.random() * 0.2
    items.append(
        _item(
            case_id,
            "memory",
            EvidenceSource.MEMORY,
            memory_service,
            "similar_incident",
            f"Historical prior suggests {memory_service}; it is not a current fact.",
            memory_similarity,
            window.start,
            None,
            {"similarity": memory_similarity},
            origin=EvidenceOrigin.HISTORICAL_PRIOR,
        )
    )
    distractor = _SERVICES[_seed(case_id + ":distractor") % len(_SERVICES)]
    if distractor not in {cause, affected}:
        items.append(
            _item(
                case_id,
                "distractor",
                EvidenceSource.METRICS,
                distractor,
                "background_noise",
                f"Weak background variation at {distractor}.",
                0.38 + rng.random() * 0.12,
                window.start + timedelta(seconds=150),
                window,
                {"anomaly_score": 0.42},
            )
        )
    return tuple(items)


def _item(
    case_id: str,
    suffix: str,
    source: EvidenceSource,
    service: str,
    signal: str,
    observation: str,
    confidence: float,
    observed_at: datetime,
    window: QueryWindow | None,
    attributes: dict[str, float],
    *,
    origin: EvidenceOrigin = EvidenceOrigin.CURRENT,
) -> Evidence:
    return Evidence(
        id=uuid5(NAMESPACE_URL, f"rootlens-eval-evidence:{case_id}:{suffix}"),
        source=source,
        origin=origin,
        service=service,
        signal=signal,
        observation=observation,
        window=window,
        supports=(f"service:{service}",),
        query_reference=f"replay://{source.value}/{case_id}/{suffix}",
        confidence=confidence,
        observed_at=observed_at,
        attributes=attributes,
        untrusted_content=source is EvidenceSource.LOGS,
    )


def _graph(
    case_id: str, cause: str, window: QueryWindow, rng: random.Random
) -> ServiceGraphSnapshot:
    nodes = tuple(
        ServiceNode(
            service=service,
            span_count=100,
            trace_count=25,
            error_count=20 if service == cause else 2,
            error_rate=0.2 if service == cause else 0.02,
        )
        for service in _SERVICES
    )
    edges = tuple(
        ServiceEdge(
            caller=caller,
            callee=callee,
            request_count=500 if callee == cause else 100,
            trace_count=25,
            failure_count=80 if callee == cause else 2,
            error_rate=0.4 if callee == cause else 0.02,
            request_rate_per_second=10,
            p50_latency_ms=25,
            p95_latency_ms=1_200 if callee == cause else 80 + rng.random() * 20,
            p99_latency_ms=1_800 if callee == cause else 120,
            first_seen=window.start,
            last_seen=window.end,
        )
        for caller, callee in _EDGES
    )
    return ServiceGraphSnapshot(
        id=uuid5(NAMESPACE_URL, f"rootlens-eval-graph:{case_id}"),
        window=window,
        trace_count=25,
        nodes=nodes,
        edges=edges,
        evidence_references=(f"replay://tempo/{case_id}",),
    )


def _signal(fault_type: FaultType) -> str:
    name = fault_type.value
    if "latency" in name or "stress" in name or "bandwidth" in name:
        return "p95_latency"
    if "kill" in name or "failure" in name or "abort" in name or "fault" in name:
        return "error_rate"
    return "request_degradation"


def _seed(value: str) -> int:
    return int.from_bytes(hashlib.sha256(value.encode()).digest()[:8], "big")


def repetition_mod(case_id: str, divisor: int) -> int:
    return _seed(case_id) % divisor

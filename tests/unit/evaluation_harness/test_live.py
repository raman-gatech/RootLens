"""Live evaluation blindness and aggregate-output tests."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest

from evaluation_harness.live import RootLensClient, _trial
from evaluation_harness.runner import aggregate_trials
from rootlens.investigation import (
    AgentMode,
    Evidence,
    EvidenceOrigin,
    EvidenceSource,
    Hypothesis,
    HypothesisStatus,
    Incident,
    Investigation,
    InvestigationStatus,
)
from rootlens.investigation.contracts import AgentRole, InvestigationUsage
from rootlens.telemetry import QueryWindow


async def test_client_sends_only_generic_incident_metadata() -> None:
    now = datetime(2026, 8, 25, 12, tzinfo=UTC)

    def handler(request: httpx.Request) -> httpx.Response:
        payload = request.read().decode()
        assert "pod_kill" not in payload
        assert "checkout" not in payload
        assert "root_cause" not in payload
        return httpx.Response(
            201,
            json=Incident(
                title="Customer request degradation",
                affected_service="frontend-proxy",
                window=QueryWindow(start=now - timedelta(minutes=2), end=now),
            ).model_dump(mode="json"),
        )

    async with RootLensClient(
        base_url="https://rootlens.test", transport=httpx.MockTransport(handler)
    ) as client:
        incident = await client.create_blind_incident(ordinal=1, started_at=now, finished_at=now)

    assert incident.affected_service == "frontend-proxy"
    assert incident.labels == {}


def test_trial_truth_is_reduced_to_aggregate_only() -> None:
    now = datetime(2026, 8, 25, 12, tzinfo=UTC)
    evidence = Evidence(
        source=EvidenceSource.METRICS,
        origin=EvidenceOrigin.CURRENT,
        service="checkout",
        signal="latency",
        observation="Latency rose during the incident window.",
        query_reference="prometheus:test",
        confidence=0.9,
    )
    investigation = Investigation(
        incident_id=uuid4(),
        mode=AgentMode.MULTI,
        provider="deterministic-v1",
        status=InvestigationStatus.COMPLETED,
        started_at=now,
        completed_at=now + timedelta(seconds=1),
        usage=InvestigationUsage(tool_calls=3, wall_time_seconds=1),
        evidence=(evidence,),
        hypotheses=(
            Hypothesis(
                id="service:checkout",
                rank=1,
                root_cause_service="checkout",
                component="checkout",
                failure_mode="latency",
                description="Checkout latency is the leading cause.",
                evidence_for=(evidence.id,),
                confidence=0.9,
                status=HypothesisStatus.SUPPORTED,
                generated_by=AgentRole.MANAGER,
            ),
        ),
    )

    trial = _trial(ordinal=1, repetition=1, ground_truth="checkout", investigation=investigation)
    metrics = aggregate_trials((trial,))

    assert metrics.top1_accuracy == 1
    assert metrics.evidence_precision == 1
    assert "ground_truth" not in metrics.model_dump_json()


def test_aggregate_rejects_empty_trial_set() -> None:
    with pytest.raises(ValueError, match="at least one trial"):
        aggregate_trials(())

"""Tests for real-model live baseline orchestration."""

from datetime import UTC, datetime, timedelta

from evaluation_harness.openai_live import (
    DEFAULT_OPENAI_MODEL,
    OPENAI_METHODS,
    OpenAILiveBaselineSuite,
)
from rootlens.investigation import (
    AgentMode,
    Evidence,
    EvidenceSource,
    Hypothesis,
    HypothesisStatus,
    Incident,
    Investigation,
    InvestigationStatus,
)
from rootlens.investigation.contracts import AgentRole, InvestigationUsage
from rootlens.investigation.provider import ProviderResult
from rootlens.telemetry import QueryWindow


class _RecordingProvider:
    name = "recording-openai"

    def __init__(self) -> None:
        self.calls: list[tuple[Incident, tuple[Evidence, ...], AgentRole]] = []

    async def synthesize(
        self, incident: Incident, evidence: tuple[Evidence, ...], *, generated_by: AgentRole
    ) -> ProviderResult:
        self.calls.append((incident, evidence, generated_by))
        supporting = (evidence[0].id,) if evidence else ()
        return ProviderResult(
            provider=self.name,
            hypotheses=(
                Hypothesis(
                    id=f"{generated_by.value}:candidate",
                    rank=1,
                    root_cause_service=evidence[0].service if evidence else "frontend-proxy",
                    component=evidence[0].service if evidence else "frontend-proxy",
                    failure_mode="request degradation",
                    description="Candidate derived only from the provided input.",
                    evidence_for=supporting,
                    confidence=0.9 if supporting else 0.1,
                    status=(HypothesisStatus.SUPPORTED if supporting else HypothesisStatus.WEAK),
                    generated_by=generated_by,
                ),
            ),
            usage=InvestigationUsage(llm_calls=1, input_tokens=10, output_tokens=5),
        )


async def test_suite_runs_five_blinded_methods_with_audited_usage() -> None:
    now = datetime(2026, 8, 25, 12, tzinfo=UTC)
    incident = Incident(
        title="Customer request degradation",
        summary="Generic blind evaluation incident.",
        affected_service="frontend-proxy",
        window=QueryWindow(start=now, end=now + timedelta(minutes=2)),
    )
    evidence = Evidence(
        source=EvidenceSource.METRICS,
        service="checkout",
        signal="error_rate",
        observation="Failures rose in the incident window.",
        query_reference="prometheus:test",
        confidence=0.9,
        attributes={"anomaly_score": 0.9},
    )
    investigation = Investigation(
        incident_id=incident.id,
        mode=AgentMode.MULTI,
        provider="deterministic-v1",
        status=InvestigationStatus.COMPLETED,
        started_at=now,
        completed_at=now + timedelta(seconds=1),
        usage=InvestigationUsage(tool_calls=5),
        evidence=(evidence,),
    )
    provider = _RecordingProvider()
    suite = OpenAILiveBaselineSuite(provider=provider, model=DEFAULT_OPENAI_MODEL)

    trials = await suite.run(
        incident=incident,
        investigation=investigation,
        ground_truth="checkout",
        case_id="live-01-001",
    )

    assert tuple(trials) == OPENAI_METHODS
    assert len(provider.calls) == 3
    assert provider.calls[0][1] == ()
    assert all("checkout" not in call[0].model_dump_json() for call in provider.calls)
    assert trials["A_alert_only"].llm_calls == 0
    assert trials["B_single_llm"].tool_calls == 0
    assert trials["C_retrieval_agent"].llm_calls == 1
    assert trials["D_multi_agent"].llm_calls == 1
    assert trials["E_rootlens"].predictions[0] == "checkout"
    assert trials["E_rootlens"].estimated_cost_usd == 0.00003
    assert all(item.ground_truth == "checkout" for item in trials.values())


def test_suite_rejects_model_without_audited_pricing() -> None:
    provider = _RecordingProvider()

    try:
        OpenAILiveBaselineSuite(provider=provider, model="unknown-model")
    except ValueError as error:
        assert "no audited price" in str(error)
    else:
        raise AssertionError("unknown model was accepted")

"""Independent remediation policy tests."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from rootlens.investigation.contracts import (
    AgentMode,
    AgentRole,
    Evidence,
    EvidenceOrigin,
    EvidenceSource,
    Hypothesis,
    HypothesisStatus,
    Incident,
    Investigation,
    InvestigationStatus,
)
from rootlens.remediation.contracts import ActionType, RemediationPlan, RiskLevel
from rootlens.remediation.policy import RemediationPolicy, policy_allows, risk_for
from rootlens.telemetry import QueryWindow
from rootlens.telemetry.contracts import PodSnapshot


def test_only_exact_stateless_pod_restart_passes_execution_policy() -> None:
    investigation, evidence = _investigation()
    plan = _plan(investigation, evidence.id)
    pod = PodSnapshot(
        namespace="otel-demo",
        name="checkout-abc-123",
        owner_kind="ReplicaSet",
        owner_name="checkout-abc",
        labels={"app.kubernetes.io/component": "checkout"},
    )
    policy = RemediationPolicy(allowed_namespaces=("otel-demo",))

    proposal = policy.evaluate_proposal(plan, investigation)
    execution = policy.evaluate_execution(
        plan.model_copy(
            update={"decided_at": datetime.now(UTC), "decided_by": "operator@example.com"}
        ),
        investigation,
        pod,
    )

    assert policy_allows(proposal)
    assert policy_allows(execution)


def test_injection_target_and_historical_only_evidence_are_rejected() -> None:
    investigation, evidence = _investigation(origin=EvidenceOrigin.HISTORICAL_PRIOR)
    plan = _plan(investigation, evidence.id).model_copy(
        update={"target": "checkout; delete namespace"}
    )

    checks = RemediationPolicy(allowed_namespaces=("otel-demo",)).evaluate_proposal(
        plan, investigation
    )

    failed = {check.rule for check in checks if not check.passed}
    assert {"exact_target", "current_evidence"}.issubset(failed)
    assert not policy_allows(checks)


def test_higher_risk_actions_are_never_level_one() -> None:
    assert risk_for(ActionType.RESTART_POD) is RiskLevel.LOW
    assert risk_for(ActionType.ROLLBACK_DEPLOYMENT) is RiskLevel.ELEVATED
    assert risk_for(ActionType.DATABASE_CHANGE) is RiskLevel.PROHIBITED


def _investigation(
    *, origin: EvidenceOrigin = EvidenceOrigin.CURRENT
) -> tuple[Investigation, Evidence]:
    start = datetime(2026, 8, 25, 12, tzinfo=UTC)
    incident = Incident(
        id=UUID(int=1),
        title="Checkout failure",
        window=QueryWindow(start=start, end=start + timedelta(minutes=5)),
    )
    evidence = Evidence(
        id=UUID(int=2),
        source=EvidenceSource.METRICS,
        origin=origin,
        service="checkout",
        signal="error_rate",
        observation="failures elevated",
        query_reference="telemetry://prometheus/test",
        confidence=0.9,
    )
    hypothesis = Hypothesis(
        id="service:checkout",
        rank=1,
        root_cause_service="checkout",
        component="checkout",
        failure_mode="request failures",
        description="supported candidate",
        evidence_for=(evidence.id,),
        confidence=0.8,
        status=HypothesisStatus.SUPPORTED,
        generated_by=AgentRole.MANAGER,
    )
    return (
        Investigation(
            id=UUID(int=3),
            incident_id=incident.id,
            mode=AgentMode.MULTI,
            provider="test",
            status=InvestigationStatus.COMPLETED,
            started_at=start,
            completed_at=start + timedelta(seconds=1),
            evidence=(evidence,),
            hypotheses=(hypothesis,),
        ),
        evidence,
    )


def _plan(investigation: Investigation, evidence_id: UUID) -> RemediationPlan:
    return RemediationPlan(
        id=UUID(int=4),
        incident_id=investigation.incident_id,
        investigation_id=investigation.id,
        action_type=ActionType.RESTART_POD,
        risk_level=RiskLevel.LOW,
        namespace="otel-demo",
        target="checkout-abc-123",
        target_service="checkout",
        rationale="Restart one unhealthy stateless checkout pod.",
        evidence_ids=(evidence_id,),
    )

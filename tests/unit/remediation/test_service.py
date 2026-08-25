"""Approval and single-pod execution workflow tests."""

from uuid import UUID

from rootlens.remediation.contracts import RemediationStatus
from rootlens.remediation.policy import RemediationPolicy
from rootlens.remediation.service import RemediationService
from rootlens.telemetry import TelemetryEnvelope
from rootlens.telemetry.contracts import PodSnapshot, QueryProvenance, TelemetrySource
from tests.unit.remediation.test_policy import _investigation, _plan


class FakeRepository:
    def __init__(self) -> None:
        self.plan = None
        self.action = None

    async def create(self, plan: object) -> object:
        self.plan = plan
        return plan

    async def update(self, plan: object) -> object:
        self.plan = plan
        return plan

    async def transition(self, plan: object, *, expected: object) -> bool:
        self.plan = plan
        return True

    async def get(self, plan_id: UUID) -> object:
        return self.plan

    async def latest(self, incident_id: UUID) -> object:
        return self.plan

    async def save_action(self, action: object) -> None:
        self.action = action


class FakeInvestigations:
    def __init__(self, investigation: object) -> None:
        self.investigation = investigation

    async def get(self, incident_id: UUID) -> object:
        return object()

    async def latest(self, incident_id: UUID) -> object:
        return self.investigation


class FakeKubernetes:
    async def list_pods(self, namespace: str) -> TelemetryEnvelope[list[PodSnapshot]]:
        return TelemetryEnvelope(
            provenance=QueryProvenance.create(source=TelemetrySource.KUBERNETES, query="/pods"),
            data=[
                PodSnapshot(
                    namespace=namespace,
                    name="checkout-abc-123",
                    owner_kind="ReplicaSet",
                    owner_name="checkout-abc",
                    labels={"app.kubernetes.io/component": "checkout"},
                )
            ],
        )


class FakeGateway:
    kubernetes = FakeKubernetes()


class FakeExecutor:
    name = "fake"

    def __init__(self) -> None:
        self.calls = 0

    async def restart_pod(self, plan: object) -> str:
        self.calls += 1
        return "pod deleted"


async def test_approved_low_risk_plan_executes_once_and_is_audited() -> None:
    investigation, evidence = _investigation()
    repository = FakeRepository()
    repository.plan = _plan(investigation, evidence.id)
    executor = FakeExecutor()
    service = RemediationService(
        repository=repository,  # type: ignore[arg-type]
        investigations=FakeInvestigations(investigation),  # type: ignore[arg-type]
        gateway=FakeGateway(),  # type: ignore[arg-type]
        policy=RemediationPolicy(allowed_namespaces=("otel-demo",)),
        executor=executor,  # type: ignore[arg-type]
    )

    result = await service.approve_and_execute(
        investigation.incident_id,
        repository.plan.id,
        actor="operator@example.com",
        reason="confirmed checkout pod is unhealthy",
    )

    assert result.status is RemediationStatus.SUCCEEDED
    assert executor.calls == 1
    assert repository.action is not None
    assert repository.action.receipt == "pod deleted"

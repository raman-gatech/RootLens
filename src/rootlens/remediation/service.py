"""Proposal, approval, verification, execution, and audit workflow."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from rootlens.investigation.errors import InvestigationError
from rootlens.investigation.service import InvestigationService
from rootlens.remediation.contracts import (
    ActionType,
    RemediationAction,
    RemediationPlan,
    RemediationStatus,
    RiskLevel,
)
from rootlens.remediation.executor import RemediationExecutor
from rootlens.remediation.policy import RemediationPolicy, policy_allows, risk_for
from rootlens.remediation.repository import RemediationRepository
from rootlens.telemetry import TelemetryGateway


class RemediationError(RuntimeError):
    """A remediation request failed validation or policy."""


class RemediationService:
    def __init__(
        self,
        *,
        repository: RemediationRepository,
        investigations: InvestigationService,
        gateway: TelemetryGateway,
        policy: RemediationPolicy,
        executor: RemediationExecutor,
    ) -> None:
        self._repository = repository
        self._investigations = investigations
        self._gateway = gateway
        self._policy = policy
        self._executor = executor

    async def latest(self, incident_id: UUID) -> RemediationPlan | None:
        await self._investigations.get(incident_id)
        return await self._repository.latest(incident_id)

    async def propose(
        self,
        incident_id: UUID,
        *,
        action_type: ActionType,
        namespace: str,
        target: str,
        target_service: str,
        rationale: str,
    ) -> RemediationPlan:
        investigation = await self._investigations.latest(incident_id)
        if investigation is None or not investigation.hypotheses:
            raise RemediationError("a completed diagnosis is required before remediation")
        top = investigation.hypotheses[0]
        evidence_ids = top.evidence_for
        risk = risk_for(action_type)
        plan = RemediationPlan(
            incident_id=incident_id,
            investigation_id=investigation.id,
            action_type=action_type,
            risk_level=risk,
            namespace=namespace,
            target=target,
            target_service=target_service,
            rationale=rationale,
            evidence_ids=evidence_ids,
            status=(
                RemediationStatus.RECOMMENDATION_ONLY
                if risk >= RiskLevel.ELEVATED
                else RemediationStatus.PROPOSED
            ),
        )
        checks = self._policy.evaluate_proposal(plan, investigation)
        if not policy_allows(checks):
            plan = plan.model_copy(update={"status": RemediationStatus.RECOMMENDATION_ONLY})
        plan = plan.model_copy(update={"policy_checks": checks})
        return await self._repository.create(plan)

    async def reject(
        self, incident_id: UUID, plan_id: UUID, *, actor: str, reason: str
    ) -> RemediationPlan:
        plan = await self._required_plan(incident_id, plan_id)
        if plan.status is not RemediationStatus.PROPOSED:
            raise RemediationError(f"cannot reject a {plan.status.value} plan")
        rejected = plan.model_copy(
            update={
                "status": RemediationStatus.REJECTED,
                "decided_at": datetime.now(UTC),
                "decided_by": actor,
                "decision_reason": reason,
            }
        )
        if not await self._repository.transition(rejected, expected=RemediationStatus.PROPOSED):
            raise RemediationError("remediation plan was already decided")
        return rejected

    async def approve_and_execute(
        self, incident_id: UUID, plan_id: UUID, *, actor: str, reason: str
    ) -> RemediationPlan:
        plan = await self._required_plan(incident_id, plan_id)
        if plan.status is not RemediationStatus.PROPOSED:
            raise RemediationError(f"cannot approve a {plan.status.value} plan")
        if plan.risk_level is not RiskLevel.LOW or plan.action_type is not ActionType.RESTART_POD:
            raise RemediationError("policy forbids execution of this action type")
        approved = plan.model_copy(
            update={
                "status": RemediationStatus.APPROVED,
                "decided_at": datetime.now(UTC),
                "decided_by": actor,
                "decision_reason": reason,
            }
        )
        if not await self._repository.transition(approved, expected=RemediationStatus.PROPOSED):
            raise RemediationError("remediation plan was already decided")
        investigation = await self._investigations.latest(incident_id)
        if investigation is None or investigation.id != approved.investigation_id:
            await self._repository.update(
                approved.model_copy(update={"status": RemediationStatus.FAILED})
            )
            raise RemediationError("the approved investigation is no longer current")
        try:
            pods = await self._gateway.kubernetes.list_pods(approved.namespace)
        except Exception as error:
            await self._repository.update(
                approved.model_copy(update={"status": RemediationStatus.FAILED})
            )
            raise RemediationError(f"could not verify target pod: {error}") from error
        pod = next((item for item in pods.data if item.name == approved.target), None)
        checks = self._policy.evaluate_execution(approved, investigation, pod)
        approved = approved.model_copy(update={"policy_checks": checks})
        if not policy_allows(checks):
            failed = approved.model_copy(update={"status": RemediationStatus.FAILED})
            await self._repository.update(failed)
            raise RemediationError("execution policy rejected the approved action")

        executing = approved.model_copy(update={"status": RemediationStatus.EXECUTING})
        if not await self._repository.transition(executing, expected=RemediationStatus.APPROVED):
            raise RemediationError("remediation plan execution was already claimed")
        started = datetime.now(UTC)
        try:
            receipt = await self._executor.restart_pod(executing)
            action_status = "succeeded"
            final_status = RemediationStatus.SUCCEEDED
        except Exception as error:
            receipt = f"{type(error).__name__}: {str(error)[:500]}"
            action_status = "failed"
            final_status = RemediationStatus.FAILED
        completed = datetime.now(UTC)
        await self._repository.save_action(
            RemediationAction(
                plan_id=plan.id,
                incident_id=incident_id,
                action_type=plan.action_type,
                namespace=plan.namespace,
                target=plan.target,
                started_at=started,
                completed_at=completed,
                status=action_status,  # type: ignore[arg-type]
                executor=self._executor.name,
                receipt=receipt,
            )
        )
        return await self._repository.update(executing.model_copy(update={"status": final_status}))

    async def _required_plan(self, incident_id: UUID, plan_id: UUID) -> RemediationPlan:
        try:
            await self._investigations.get(incident_id)
        except InvestigationError as error:
            raise RemediationError(str(error)) from error
        plan = await self._repository.get(plan_id)
        if plan is None or plan.incident_id != incident_id:
            raise RemediationError("remediation plan does not exist for this incident")
        return plan

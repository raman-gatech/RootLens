"""Independent remediation policy engine; it never executes actions."""

from __future__ import annotations

import re

from rootlens.investigation import EvidenceOrigin, Investigation
from rootlens.remediation.contracts import (
    ActionType,
    PolicyCheck,
    RemediationPlan,
    RiskLevel,
)
from rootlens.telemetry.contracts import PodSnapshot

_DNS_LABEL = re.compile(r"^[a-z0-9](?:[-a-z0-9]{0,61}[a-z0-9])?$")
_RESOURCE_NAME = re.compile(r"^[a-z0-9](?:[-.a-z0-9]{0,251}[a-z0-9])?$")


def risk_for(action: ActionType) -> RiskLevel:
    return {
        ActionType.RESTART_POD: RiskLevel.LOW,
        ActionType.RESTART_DEPLOYMENT: RiskLevel.ELEVATED,
        ActionType.SCALE_DEPLOYMENT: RiskLevel.ELEVATED,
        ActionType.ROLLBACK_DEPLOYMENT: RiskLevel.ELEVATED,
        ActionType.DATABASE_CHANGE: RiskLevel.PROHIBITED,
        ActionType.SECRET_CHANGE: RiskLevel.PROHIBITED,
        ActionType.NETWORK_POLICY_CHANGE: RiskLevel.PROHIBITED,
    }[action]


class RemediationPolicy:
    def __init__(self, *, allowed_namespaces: tuple[str, ...]) -> None:
        self._allowed_namespaces = frozenset(allowed_namespaces)

    def evaluate_proposal(
        self, plan: RemediationPlan, investigation: Investigation
    ) -> tuple[PolicyCheck, ...]:
        current_ids = {
            item.id for item in investigation.evidence if item.origin is EvidenceOrigin.CURRENT
        }
        top = investigation.hypotheses[0] if investigation.hypotheses else None
        return (
            PolicyCheck(
                rule="namespace_allowlist",
                passed=plan.namespace in self._allowed_namespaces
                and bool(_DNS_LABEL.fullmatch(plan.namespace)),
                explanation="Target namespace must be explicitly allowed and syntactically valid.",
            ),
            PolicyCheck(
                rule="exact_target",
                passed=bool(_RESOURCE_NAME.fullmatch(plan.target)),
                explanation=(
                    "A concrete Kubernetes resource name is required; selectors are forbidden."
                ),
            ),
            PolicyCheck(
                rule="current_evidence",
                passed=bool(plan.evidence_ids) and set(plan.evidence_ids).issubset(current_ids),
                explanation="Every remediation claim must cite current-incident evidence.",
            ),
            PolicyCheck(
                rule="diagnosis_confidence",
                passed=top is not None
                and top.confidence >= 0.35
                and top.root_cause_service == plan.target_service,
                explanation="The target service must be the top evidence-ranked diagnosis.",
            ),
            PolicyCheck(
                rule="action_scope",
                passed=plan.action_type is ActionType.RESTART_POD,
                explanation=(
                    "Only one stateless pod restart is executable; all other actions are advice."
                ),
            ),
        )

    def evaluate_execution(
        self,
        plan: RemediationPlan,
        investigation: Investigation,
        pod: PodSnapshot | None,
    ) -> tuple[PolicyCheck, ...]:
        checks = list(self.evaluate_proposal(plan, investigation))
        checks.extend(
            (
                PolicyCheck(
                    rule="human_approval",
                    passed=plan.decided_by is not None and plan.decided_at is not None,
                    explanation="A named human approval is mandatory before execution.",
                ),
                PolicyCheck(
                    rule="stateless_controller",
                    passed=pod is not None and pod.owner_kind == "ReplicaSet",
                    explanation=(
                        "The target pod must be controlled by a ReplicaSet, never a StatefulSet."
                    ),
                ),
                PolicyCheck(
                    rule="pod_identity",
                    passed=pod is not None
                    and pod.name == plan.target
                    and pod.namespace == plan.namespace,
                    explanation="The observed pod must exactly match the approved target.",
                ),
                PolicyCheck(
                    rule="pod_service_alignment",
                    passed=pod is not None
                    and plan.target_service
                    in {
                        pod.labels.get("app.kubernetes.io/component"),
                        pod.labels.get("app.kubernetes.io/name"),
                        pod.labels.get("app"),
                    },
                    explanation=(
                        "The exact pod's labels must identify the diagnosed target service."
                    ),
                ),
            )
        )
        return tuple(checks)


def policy_allows(checks: tuple[PolicyCheck, ...]) -> bool:
    return bool(checks) and all(check.passed for check in checks)

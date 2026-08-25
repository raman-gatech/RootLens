"""Typed remediation plans, decisions, policy checks, and action receipts."""

from datetime import UTC, datetime
from enum import IntEnum, StrEnum
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class RiskLevel(IntEnum):
    READ_ONLY = 0
    LOW = 1
    ELEVATED = 2
    PROHIBITED = 3


class ActionType(StrEnum):
    RESTART_POD = "restart_pod"
    RESTART_DEPLOYMENT = "restart_deployment"
    SCALE_DEPLOYMENT = "scale_deployment"
    ROLLBACK_DEPLOYMENT = "rollback_deployment"
    DATABASE_CHANGE = "database_change"
    # This enum value names an action category; it is not a credential.
    SECRET_CHANGE = "secret_change"  # nosec B105
    NETWORK_POLICY_CHANGE = "network_policy_change"


class RemediationStatus(StrEnum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTING = "executing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    RECOMMENDATION_ONLY = "recommendation_only"


class PolicyCheck(BaseModel):
    model_config = ConfigDict(frozen=True)

    rule: str
    passed: bool
    explanation: str


class RemediationPlan(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: Literal["1"] = "1"
    id: UUID = Field(default_factory=uuid4)
    incident_id: UUID
    investigation_id: UUID
    action_type: ActionType
    risk_level: RiskLevel
    namespace: str = Field(min_length=1, max_length=63)
    target: str = Field(min_length=1, max_length=253)
    target_service: str = Field(min_length=1, max_length=160)
    rationale: str = Field(min_length=1, max_length=2_000)
    evidence_ids: tuple[UUID, ...]
    status: RemediationStatus = RemediationStatus.PROPOSED
    approval_required: bool = True
    policy_checks: tuple[PolicyCheck, ...] = ()
    proposed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    decided_at: datetime | None = None
    decided_by: str | None = None
    decision_reason: str | None = None


class RemediationAction(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=uuid4)
    plan_id: UUID
    incident_id: UUID
    action_type: ActionType
    namespace: str
    target: str
    started_at: datetime
    completed_at: datetime
    status: Literal["succeeded", "failed"]
    executor: str
    receipt: str

"""Typed incident, evidence, hypothesis, and agent-run contracts."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from rootlens.telemetry import QueryWindow
from rootlens.topology import ServiceGraphSnapshot


class IncidentSeverity(StrEnum):
    SEV1 = "sev1"
    SEV2 = "sev2"
    SEV3 = "sev3"
    SEV4 = "sev4"


class IncidentStatus(StrEnum):
    OPEN = "open"
    INVESTIGATING = "investigating"
    DIAGNOSED = "diagnosed"
    MITIGATED = "mitigated"
    CLOSED = "closed"


class AgentMode(StrEnum):
    SINGLE = "single_agent"
    MULTI = "multi_agent"


class InvestigationStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    BUDGET_EXHAUSTED = "budget_exhausted"


class EvidenceSource(StrEnum):
    METRICS = "metrics"
    TRACES = "traces"
    LOGS = "logs"
    CHANGES = "changes"
    KUBERNETES = "kubernetes"
    TOPOLOGY = "topology"
    MEMORY = "memory"


class EvidenceOrigin(StrEnum):
    CURRENT = "current_incident"
    HISTORICAL_PRIOR = "historical_prior"


class HypothesisStatus(StrEnum):
    ACTIVE = "active"
    SUPPORTED = "supported"
    WEAK = "weak"
    REJECTED = "rejected"
    CONFIRMED = "confirmed"


class AgentRole(StrEnum):
    SINGLE = "single_agent"
    MANAGER = "manager"
    METRICS = "metrics_specialist"
    TRACES = "trace_specialist"
    LOGS = "log_specialist"
    CHANGES = "change_specialist"
    VERIFIER = "verifier"
    MEMORY = "memory_retriever"


class Incident(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: Literal["1"] = "1"
    id: UUID = Field(default_factory=uuid4)
    title: str = Field(min_length=1, max_length=240)
    summary: str = Field(default="", max_length=4_000)
    affected_service: str | None = Field(default=None, max_length=120)
    severity: IncidentSeverity = IncidentSeverity.SEV2
    status: IncidentStatus = IncidentStatus.OPEN
    window: QueryWindow
    labels: dict[str, str] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Alert(BaseModel):
    """Persisted intake event associated with a normalized incident."""

    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=uuid4)
    incident_id: UUID
    source: str = Field(min_length=1, max_length=80)
    status: str = Field(min_length=1, max_length=40)
    labels: dict[str, str] = Field(default_factory=dict)
    annotations: dict[str, str] = Field(default_factory=dict)
    starts_at: datetime
    ends_at: datetime | None = None
    received_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Evidence(BaseModel):
    """A current observation or explicitly isolated historical prior."""

    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=uuid4)
    source: EvidenceSource
    origin: EvidenceOrigin = EvidenceOrigin.CURRENT
    service: str | None = None
    signal: str = Field(min_length=1, max_length=160)
    observation: str = Field(min_length=1, max_length=2_000)
    window: QueryWindow | None = None
    supports: tuple[str, ...] = ()
    contradicts: tuple[str, ...] = ()
    query_reference: str = Field(min_length=1, max_length=1_000)
    confidence: float = Field(ge=0, le=1)
    observed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    attributes: dict[str, Any] = Field(default_factory=dict)
    untrusted_content: bool = False


class CausalScore(BaseModel):
    model_config = ConfigDict(frozen=True)

    anomaly_strength: float = Field(default=0, ge=0, le=1)
    temporal_precedence: float = Field(default=0, ge=0, le=1)
    trace_criticality: float = Field(default=0, ge=0, le=1)
    graph_consistency: float = Field(default=0, ge=0, le=1)
    log_evidence: float = Field(default=0, ge=0, le=1)
    recent_change: float = Field(default=0, ge=0, le=1)
    historical_similarity: float = Field(default=0, ge=0, le=1)
    contradiction_penalty: float = Field(default=0, ge=0, le=1)
    total: float = Field(default=0, ge=0, le=1)


class Hypothesis(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1, max_length=160)
    rank: int = Field(ge=1)
    root_cause_service: str = Field(min_length=1, max_length=160)
    component: str = Field(min_length=1, max_length=160)
    failure_mode: str = Field(min_length=1, max_length=240)
    description: str = Field(min_length=1, max_length=2_000)
    predicted_observations: tuple[str, ...] = ()
    evidence_for: tuple[UUID, ...] = ()
    evidence_against: tuple[UUID, ...] = ()
    confidence: float = Field(ge=0, le=1)
    status: HypothesisStatus
    causal_score: CausalScore = Field(default_factory=CausalScore)
    generated_by: AgentRole

    @model_validator(mode="after")
    def require_support_for_positive_status(self) -> Hypothesis:
        if self.status in {HypothesisStatus.SUPPORTED, HypothesisStatus.CONFIRMED}:
            if not self.evidence_for:
                raise ValueError("supported hypotheses require at least one evidence reference")
        return self


class ToolCallAudit(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=uuid4)
    incident_id: UUID
    investigation_id: UUID
    agent_id: AgentRole
    tool_name: str
    arguments: dict[str, Any]
    started_at: datetime
    completed_at: datetime
    status: Literal["success", "error"]
    result_bytes: int = Field(default=0, ge=0)
    evidence_ids: tuple[UUID, ...] = ()
    error: str | None = None


class AgentRun(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=uuid4)
    agent_id: AgentRole
    started_at: datetime
    completed_at: datetime
    status: Literal["completed", "failed"]
    input_evidence_ids: tuple[UUID, ...] = ()
    output_hypothesis_ids: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()


class InvestigationBudget(BaseModel):
    model_config = ConfigDict(frozen=True)

    max_llm_calls: int = Field(default=30, ge=0, le=100)
    max_tool_calls: int = Field(default=100, ge=1, le=500)
    max_rounds: int = Field(default=5, ge=1, le=20)
    max_duration_seconds: int = Field(default=300, ge=1, le=1_800)


class InvestigationUsage(BaseModel):
    model_config = ConfigDict(frozen=True)

    llm_calls: int = Field(default=0, ge=0)
    tool_calls: int = Field(default=0, ge=0)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    estimated_cost_usd: float = Field(default=0, ge=0)
    telemetry_bytes: int = Field(default=0, ge=0)
    wall_time_seconds: float = Field(default=0, ge=0)


class Investigation(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: Literal["1"] = "1"
    id: UUID = Field(default_factory=uuid4)
    incident_id: UUID
    mode: AgentMode
    provider: str
    status: InvestigationStatus
    started_at: datetime
    completed_at: datetime | None = None
    budget: InvestigationBudget = Field(default_factory=InvestigationBudget)
    usage: InvestigationUsage = Field(default_factory=InvestigationUsage)
    evidence: tuple[Evidence, ...] = ()
    hypotheses: tuple[Hypothesis, ...] = ()
    agent_runs: tuple[AgentRun, ...] = ()
    tool_calls: tuple[ToolCallAudit, ...] = ()
    graph: ServiceGraphSnapshot | None = None
    warnings: tuple[str, ...] = ()


class EvidenceBundle(BaseModel):
    model_config = ConfigDict(frozen=True)

    agent: AgentRole
    evidence: tuple[Evidence, ...]
    tool_calls: tuple[ToolCallAudit, ...]
    graph: ServiceGraphSnapshot | None = None
    warnings: tuple[str, ...] = ()


class HistoricalIncident(BaseModel):
    """Human-confirmed incident outcome stored for similarity retrieval."""

    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=uuid4)
    source_incident_id: UUID | None = None
    title: str = Field(min_length=1, max_length=240)
    summary: str = Field(default="", max_length=4_000)
    root_cause_service: str = Field(min_length=1, max_length=160)
    failure_mode: str = Field(min_length=1, max_length=240)
    resolution: str = Field(min_length=1, max_length=4_000)
    services: tuple[str, ...] = ()
    symptoms: tuple[str, ...] = ()
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class SimilarIncident(BaseModel):
    model_config = ConfigDict(frozen=True)

    incident: HistoricalIncident
    similarity: float = Field(ge=-1, le=1)

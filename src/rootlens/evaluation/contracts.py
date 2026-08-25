"""Publishable aggregate benchmark contracts with no incident ground truth."""

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class EvaluationMetrics(BaseModel):
    model_config = ConfigDict(frozen=True)

    trials: int = Field(ge=1)
    top1_accuracy: float = Field(ge=0, le=1)
    top3_accuracy: float = Field(ge=0, le=1)
    mean_latency_ms: float = Field(ge=0)
    p95_latency_ms: float = Field(ge=0)
    evidence_precision: float = Field(ge=0, le=1)
    hallucinated_evidence_rate: float = Field(ge=0, le=1)
    mean_tool_calls: float = Field(ge=0)
    mean_llm_calls: float = Field(ge=0)
    mean_input_tokens: float = Field(ge=0)
    mean_output_tokens: float = Field(ge=0)
    estimated_cost_usd: float = Field(ge=0)
    safety_violations: int = Field(ge=0)


class EvaluationReport(BaseModel):
    """Aggregate-only report safe to publish to the RootLens runtime."""

    model_config = ConfigDict(frozen=True)

    schema_version: Literal["1"] = "1"
    id: UUID = Field(default_factory=uuid4)
    dataset_version: str = Field(min_length=1, max_length=120)
    execution_mode: Literal["offline_deterministic_replay", "live"]
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    fault_type_count: int = Field(ge=1)
    repetitions_per_fault: int = Field(ge=1)
    incident_count: int = Field(ge=1)
    methods: dict[str, EvaluationMetrics]
    ablations: dict[str, EvaluationMetrics]
    notes: tuple[str, ...] = ()

"""Private benchmark cases and trial observations."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from experiment_controller.contracts import FaultType
from rootlens.investigation import Evidence, Incident
from rootlens.topology import ServiceGraphSnapshot


class BenchmarkCase(BaseModel):
    """Private case including ground truth; never serialize into runtime reports."""

    model_config = ConfigDict(frozen=True)

    case_id: str
    fault_type: FaultType
    repetition: int = Field(ge=1)
    root_cause_service: str
    incident: Incident
    evidence: tuple[Evidence, ...]
    graph: ServiceGraphSnapshot
    candidates: tuple[str, ...]


class TrialResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    case_id: str
    method: str
    predictions: tuple[str, ...]
    claimed_evidence_ids: tuple[UUID, ...]
    valid_evidence_ids: tuple[UUID, ...]
    latency_ms: float = Field(ge=0)
    tool_calls: int = Field(ge=0)
    llm_calls: int = Field(ge=0)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    estimated_cost_usd: float = Field(ge=0)
    safety_violations: int = Field(ge=0)
    ground_truth: str


AblationName = Literal[
    "no_graph",
    "no_traces",
    "no_logs",
    "no_anomaly",
    "no_verifier",
    "no_memory",
    "single_agent",
]

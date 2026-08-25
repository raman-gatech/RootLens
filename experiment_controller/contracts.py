"""Schemas for benchmark-only fault experiments and hidden ground truth."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Self
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


class FaultType(StrEnum):
    POD_KILL = "pod_kill"
    CPU_STRESS = "cpu_stress"
    NETWORK_LATENCY = "network_latency"
    PACKET_LOSS = "packet_loss"
    HTTP_DELAY = "http_delay"


class ExperimentSpec(BaseModel):
    """Complete fault truth. This model must never enter RootLens APIs or telemetry."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    experiment_id: UUID = Field(default_factory=uuid4)
    fault_type: FaultType
    namespace: str = "otel-demo"
    target_service: str
    target_dependency: str | None = None
    duration_seconds: int = Field(default=30, ge=5, le=600)
    latency_ms: int = Field(default=1_500, ge=1, le=30_000)
    jitter_ms: int = Field(default=0, ge=0, le=10_000)
    packet_loss_percent: int = Field(default=30, ge=1, le=100)
    cpu_workers: int = Field(default=1, ge=1, le=8)
    cpu_load_percent: int = Field(default=80, ge=1, le=100)
    http_port: int = Field(default=8080, ge=1, le=65_535)
    http_method: str = "GET"
    http_path: str = "*"

    @model_validator(mode="after")
    def validate_dependency_fault(self) -> Self:
        if self.fault_type in {FaultType.NETWORK_LATENCY, FaultType.PACKET_LOSS}:
            if not self.target_dependency:
                raise ValueError("network faults require target_dependency")
            if self.target_dependency == self.target_service:
                raise ValueError("network fault source and dependency must differ")
        return self

    @property
    def resource_name(self) -> str:
        suffix = self.experiment_id.hex[:12]
        return f"rootlens-{self.fault_type.value.replace('_', '-')}-{suffix}"


class GroundTruthEventType(StrEnum):
    PLANNED = "planned"
    APPLIED = "applied"
    RECOVERED = "recovered"
    FAILED = "failed"


class GroundTruthEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    event: GroundTruthEventType
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    spec: ExperimentSpec
    manifest_sha256: str
    detail: str | None = None


class PublicExperimentReceipt(BaseModel):
    """Non-sensitive lifecycle receipt that intentionally excludes fault truth."""

    experiment_id: UUID
    status: GroundTruthEventType
    started_at: datetime
    finished_at: datetime | None = None

"""Typed contracts for reproducible anomaly analyses."""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from rootlens.telemetry import MetricSample, QueryWindow


class SignalName(StrEnum):
    REQUEST_RATE = "request_rate"
    ERROR_RATE = "error_rate"
    P95_LATENCY = "p95_latency"


class DetectorName(StrEnum):
    STATISTICAL = "statistical"
    ISOLATION_FOREST = "isolation_forest"


class AnomalyDirection(StrEnum):
    HIGH = "high"
    LOW = "low"


class MetricSignalSeries(BaseModel):
    """One service/signal split into uncontaminated baseline and incident samples."""

    model_config = ConfigDict(frozen=True)

    service: str = Field(min_length=1)
    signal: SignalName
    baseline_samples: tuple[MetricSample, ...]
    incident_samples: tuple[MetricSample, ...]
    evidence_references: tuple[str, ...]


class BaselineStatistics(BaseModel):
    model_config = ConfigDict(frozen=True)

    sample_count: int = Field(ge=1)
    mean: float
    standard_deviation: float = Field(ge=0)
    median: float
    median_absolute_deviation: float = Field(ge=0)
    final_ewma: float


class RankedAnomaly(BaseModel):
    model_config = ConfigDict(frozen=True)

    rank: int = Field(ge=1)
    service: str
    signal: SignalName
    score: float = Field(ge=0, le=1)
    statistical_score: float = Field(ge=0, le=1)
    isolation_forest_score: float | None = Field(default=None, ge=0, le=1)
    direction: AnomalyDirection
    anomaly_start_time: datetime
    peak_timestamp: datetime
    peak_value: float
    max_absolute_robust_z_score: float = Field(ge=0)
    max_absolute_standard_z_score: float = Field(ge=0)
    max_absolute_ewma_z_score: float = Field(ge=0)
    baseline: BaselineStatistics
    incident_sample_count: int = Field(ge=1)
    evidence_references: tuple[str, ...]


class AnomalyAnalysisSnapshot(BaseModel):
    """Immutable ranked output for one baseline/incident comparison."""

    model_config = ConfigDict(frozen=True)

    schema_version: Literal["1"] = "1"
    algorithm_version: Literal["stat-iforest-v1"] = "stat-iforest-v1"
    id: UUID = Field(default_factory=uuid4)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    baseline_window: QueryWindow
    incident_window: QueryWindow
    detectors: tuple[DetectorName, ...]
    evaluated_series: int = Field(ge=0)
    minimum_score: float = Field(ge=0, le=1)
    anomalies: tuple[RankedAnomaly, ...]
    evidence_references: tuple[str, ...]
    warnings: tuple[str, ...] = ()

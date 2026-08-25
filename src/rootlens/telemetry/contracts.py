"""Typed, provenance-bearing contracts shared by all telemetry backends."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class TelemetrySource(StrEnum):
    PROMETHEUS = "prometheus"
    TEMPO = "tempo"
    LOKI = "loki"
    KUBERNETES = "kubernetes"


class QueryWindow(BaseModel):
    """A closed UTC-aware evidence collection interval."""

    model_config = ConfigDict(frozen=True)

    start: datetime
    end: datetime

    @model_validator(mode="after")
    def validate_interval(self) -> QueryWindow:
        if self.start.tzinfo is None or self.end.tzinfo is None:
            raise ValueError("query window timestamps must be timezone-aware")
        if self.start >= self.end:
            raise ValueError("query window start must precede end")
        return self


class QueryProvenance(BaseModel):
    """The reproducible origin of a normalized telemetry result."""

    model_config = ConfigDict(frozen=True)

    source: TelemetrySource
    query: str
    parameters: dict[str, str] = Field(default_factory=dict)
    window: QueryWindow | None = None
    retrieved_at: datetime
    reference: str

    @classmethod
    def create(
        cls,
        *,
        source: TelemetrySource,
        query: str,
        parameters: dict[str, str] | None = None,
        window: QueryWindow | None = None,
        retrieved_at: datetime | None = None,
    ) -> QueryProvenance:
        fetched = retrieved_at or datetime.now(UTC)
        safe_parameters = parameters or {}
        payload = {
            "source": source.value,
            "query": query,
            "parameters": safe_parameters,
            "window": window.model_dump(mode="json") if window else None,
            "retrieved_at": fetched.isoformat(),
        }
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return cls(
            source=source,
            query=query,
            parameters=safe_parameters,
            window=window,
            retrieved_at=fetched,
            reference=f"telemetry://{source.value}/{digest}",
        )


class TelemetryEnvelope[T](BaseModel):
    """Normalized evidence accompanied by its source and retrieval details."""

    model_config = ConfigDict(frozen=True)

    status: Literal["success"] = "success"
    provenance: QueryProvenance
    data: T
    warnings: tuple[str, ...] = ()


class MetricSample(BaseModel):
    timestamp: datetime
    value: float


class MetricSeries(BaseModel):
    labels: dict[str, str]
    samples: list[MetricSample]


class LogEntry(BaseModel):
    timestamp: datetime
    line: str


class LogStream(BaseModel):
    labels: dict[str, str]
    entries: list[LogEntry]


class TraceSummary(BaseModel):
    trace_id: str
    root_service_name: str | None = None
    root_trace_name: str | None = None
    start_time: datetime | None = None
    duration_seconds: float | None = None


class SpanRecord(BaseModel):
    trace_id: str
    span_id: str
    parent_span_id: str | None = None
    service_name: str | None = None
    name: str
    kind: str | None = None
    start_time: datetime
    end_time: datetime
    status_code: str | None = None
    attributes: dict[str, str | int | float | bool] = Field(default_factory=dict)


class PodSnapshot(BaseModel):
    namespace: str
    name: str
    uid: str | None = None
    phase: str | None = None
    node_name: str | None = None
    labels: dict[str, str] = Field(default_factory=dict)
    created_at: datetime | None = None


class DeploymentSnapshot(BaseModel):
    namespace: str
    name: str
    uid: str | None = None
    generation: int | None = None
    observed_generation: int | None = None
    replicas: int | None = None
    ready_replicas: int | None = None
    labels: dict[str, str] = Field(default_factory=dict)
    annotations: dict[str, str] = Field(default_factory=dict)
    created_at: datetime | None = None


class KubernetesEvent(BaseModel):
    namespace: str
    name: str
    event_type: str | None = None
    reason: str | None = None
    message: str | None = None
    involved_kind: str | None = None
    involved_name: str | None = None
    count: int | None = None
    first_seen: datetime | None = None
    last_seen: datetime | None = None


class ChangeEvent(BaseModel):
    """A deployment-related fact, without causal interpretation."""

    timestamp: datetime | None = None
    namespace: str
    resource_kind: str
    resource_name: str
    change_type: str
    details: dict[str, str | int | float | bool] = Field(default_factory=dict)

"""Typed contracts for reconstructed service dependency graphs."""

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from rootlens.telemetry import QueryWindow


class ServiceNode(BaseModel):
    model_config = ConfigDict(frozen=True)

    service: str
    span_count: int = Field(ge=0)
    trace_count: int = Field(ge=0)
    error_count: int = Field(ge=0)
    error_rate: float = Field(ge=0, le=1)


class ServiceEdge(BaseModel):
    model_config = ConfigDict(frozen=True)

    caller: str
    callee: str
    request_count: int = Field(ge=1)
    trace_count: int = Field(ge=1)
    failure_count: int = Field(ge=0)
    error_rate: float = Field(ge=0, le=1)
    request_rate_per_second: float = Field(ge=0)
    p50_latency_ms: float = Field(ge=0)
    p95_latency_ms: float = Field(ge=0)
    p99_latency_ms: float = Field(ge=0)
    first_seen: datetime
    last_seen: datetime


class ServiceGraphSnapshot(BaseModel):
    """An immutable topology reconstruction for one telemetry window."""

    model_config = ConfigDict(frozen=True)

    schema_version: Literal["1"] = "1"
    id: UUID = Field(default_factory=uuid4)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    window: QueryWindow
    trace_count: int = Field(ge=0)
    nodes: tuple[ServiceNode, ...]
    edges: tuple[ServiceEdge, ...]
    evidence_references: tuple[str, ...]
    warnings: tuple[str, ...] = ()


class ServiceSet(BaseModel):
    service: str
    services: tuple[str, ...]


class ServicePath(BaseModel):
    source: str
    target: str
    services: tuple[str, ...]

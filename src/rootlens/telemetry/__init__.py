"""Backend-neutral telemetry retrieval gateway."""

from rootlens.telemetry.contracts import (
    MetricSample,
    MetricSeries,
    QueryProvenance,
    QueryWindow,
    TelemetryEnvelope,
    TelemetrySource,
)
from rootlens.telemetry.errors import TelemetryErrorCode, TelemetryQueryError
from rootlens.telemetry.gateway import TelemetryGateway

__all__ = [
    "MetricSample",
    "MetricSeries",
    "QueryProvenance",
    "QueryWindow",
    "TelemetryEnvelope",
    "TelemetryErrorCode",
    "TelemetryGateway",
    "TelemetryQueryError",
    "TelemetrySource",
]

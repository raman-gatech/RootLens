"""OpenTelemetry bootstrap for RootLens itself."""

from urllib.parse import urlsplit

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from rootlens.config import Settings


def configure_telemetry(settings: Settings) -> None:
    """Configure OTLP tracing and metrics once during application startup."""

    if not settings.telemetry_enabled:
        return

    resource = Resource.create(
        {
            "service.name": settings.service_name,
            "service.version": settings.service_version,
            "deployment.environment.name": settings.environment,
        }
    )
    insecure = otlp_uses_insecure_transport(settings.otlp_endpoint)
    trace_provider = TracerProvider(resource=resource)
    trace_provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=settings.otlp_endpoint, insecure=insecure))
    )
    trace.set_tracer_provider(trace_provider)

    metric_reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(endpoint=settings.otlp_endpoint, insecure=insecure),
        export_interval_millis=10_000,
    )
    metrics.set_meter_provider(MeterProvider(resource=resource, metric_readers=[metric_reader]))


def otlp_uses_insecure_transport(endpoint: str) -> bool:
    """Return whether an explicit OTLP endpoint requests plaintext transport."""
    parsed = urlsplit(endpoint)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("OTLP endpoint must be an absolute HTTP(S) URL")
    return parsed.scheme == "http"

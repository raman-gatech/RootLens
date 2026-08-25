"""Prometheus feature collection tests."""

from datetime import UTC, datetime, timedelta

from rootlens.anomaly.catalog import SIGNAL_CATALOG
from rootlens.anomaly.contracts import SignalName
from rootlens.anomaly.service import _collect_series
from rootlens.telemetry import (
    MetricSample,
    MetricSeries,
    QueryProvenance,
    QueryWindow,
    TelemetryEnvelope,
    TelemetrySource,
)


def test_collects_only_services_present_in_baseline_and_incident_with_provenance() -> None:
    start = datetime(2026, 8, 25, 12, tzinfo=UTC)
    baseline = envelope(
        "baseline",
        start,
        [series("payment", start, [100, 101]), series("orphan", start, [1, 2])],
    )
    incident = envelope(
        "incident",
        start + timedelta(minutes=1),
        [series("payment", start + timedelta(minutes=1), [500, 600])],
    )

    collected, warnings = _collect_series(
        (SIGNAL_CATALOG[SignalName.P95_LATENCY],),
        (baseline, incident),
    )

    assert len(collected) == 1
    assert collected[0].service == "payment"
    assert collected[0].evidence_references == (
        baseline.provenance.reference,
        incident.provenance.reference,
    )
    assert warnings == ("p95_latency: skipped services absent from one window: orphan",)


def series(service: str, start: datetime, values: list[float]) -> MetricSeries:
    return MetricSeries(
        labels={"server": service},
        samples=[
            MetricSample(timestamp=start + timedelta(seconds=index * 30), value=value)
            for index, value in enumerate(values)
        ],
    )


def envelope(
    query: str,
    start: datetime,
    data: list[MetricSeries],
) -> TelemetryEnvelope[list[MetricSeries]]:
    window = QueryWindow(start=start, end=start + timedelta(minutes=1))
    return TelemetryEnvelope(
        provenance=QueryProvenance.create(
            source=TelemetrySource.PROMETHEUS,
            query=query,
            window=window,
            retrieved_at=window.end,
        ),
        data=data,
    )

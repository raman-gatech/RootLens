"""Interpretable statistical detector tests."""

from datetime import UTC, datetime, timedelta

from rootlens.anomaly import MetricSignalSeries, SignalName
from rootlens.anomaly.statistical import StatisticalDetector
from rootlens.telemetry import MetricSample


def test_detects_spike_and_estimates_first_anomalous_sample() -> None:
    start = datetime(2026, 8, 25, 12, tzinfo=UTC)
    series = metric_series(
        service="payment",
        signal=SignalName.P95_LATENCY,
        start=start,
        baseline=[98, 100, 101, 99, 102, 98, 100, 101, 99, 100, 102, 98],
        incident=[100, 101, 650, 620],
    )

    result = StatisticalDetector().score(series)

    expected_start = start + timedelta(seconds=14 * 30)
    assert result.anomaly_start_time == expected_start
    assert result.peak_value == 650
    assert result.score == 1
    assert result.direction.value == "high"
    assert result.max_absolute_robust_z_score > 100
    assert result.baseline.median == 100
    assert result.baseline.sample_count == 12


def test_zero_variance_baseline_is_stable_but_flags_a_real_change() -> None:
    start = datetime(2026, 8, 25, 12, tzinfo=UTC)
    detector = StatisticalDetector()

    stable = detector.score(
        metric_series(
            service="checkout",
            signal=SignalName.ERROR_RATE,
            start=start,
            baseline=[0] * 10,
            incident=[0, 0, 0],
        )
    )
    changed = detector.score(
        metric_series(
            service="checkout",
            signal=SignalName.ERROR_RATE,
            start=start,
            baseline=[0] * 10,
            incident=[0, 0.4, 0.5],
        )
    )

    assert stable.score == 0
    assert stable.anomaly_start_time is None
    assert changed.score == 1
    assert changed.anomaly_start_time is not None


def test_floating_point_noise_on_effectively_constant_histogram_is_not_anomaly() -> None:
    start = datetime(2026, 8, 25, 12, tzinfo=UTC)
    series = metric_series(
        service="flagd",
        signal=SignalName.P95_LATENCY,
        start=start,
        baseline=[95.0, 94.99999999999999, 95.00000000000001] * 4,
        incident=[95.00000000000001, 95.0, 94.99999999999999],
    )

    result = StatisticalDetector().score(series)

    assert result.score == 0
    assert result.anomaly_start_time is None


def test_baseline_outlier_does_not_poison_ewma_forecast() -> None:
    start = datetime(2026, 8, 25, 12, tzinfo=UTC)
    series = metric_series(
        service="flagd",
        signal=SignalName.P95_LATENCY,
        start=start,
        baseline=[97, 98, 97, 98, 97, 98, 97, 98, 2_500, 97, 98, 97],
        incident=[98, 97, 98],
    )

    result = StatisticalDetector().score(series)

    assert result.score < 0.5
    assert result.anomaly_start_time is None


def metric_series(
    *,
    service: str,
    signal: SignalName,
    start: datetime,
    baseline: list[float],
    incident: list[float],
) -> MetricSignalSeries:
    step = timedelta(seconds=30)
    baseline_samples = tuple(
        MetricSample(timestamp=start + index * step, value=value)
        for index, value in enumerate(baseline)
    )
    incident_start = start + len(baseline) * step
    incident_samples = tuple(
        MetricSample(timestamp=incident_start + index * step, value=value)
        for index, value in enumerate(incident)
    )
    return MetricSignalSeries(
        service=service,
        signal=signal,
        baseline_samples=baseline_samples,
        incident_samples=incident_samples,
        evidence_references=(f"telemetry://prometheus/{service}-{signal.value}",),
    )

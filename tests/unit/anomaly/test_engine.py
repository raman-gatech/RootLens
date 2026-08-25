"""Combined statistical and Isolation Forest ranking tests."""

from datetime import UTC, datetime, timedelta

from rootlens.anomaly import AnomalyEngine, DetectorName, SignalName
from rootlens.anomaly.isolation_forest import IsolationForestDetector
from rootlens.telemetry import QueryWindow
from tests.unit.anomaly.test_statistical import metric_series


def test_ranks_incident_anomalies_by_service_and_signal_deterministically() -> None:
    start = datetime(2026, 8, 25, 12, tzinfo=UTC)
    baseline_values = [98, 101, 100, 99, 102, 98, 101, 100, 99, 102, 100, 99]
    series = (
        metric_series(
            service="payment",
            signal=SignalName.P95_LATENCY,
            start=start,
            baseline=baseline_values,
            incident=[100, 105, 650, 620],
        ),
        metric_series(
            service="payment",
            signal=SignalName.REQUEST_RATE,
            start=start,
            baseline=[20, 21, 19, 20, 20, 21, 19, 20, 20, 21, 19, 20],
            incident=[20, 20, 19, 20],
        ),
        metric_series(
            service="checkout",
            signal=SignalName.P95_LATENCY,
            start=start,
            baseline=[180, 182, 178, 181, 179, 180, 182, 178, 181, 179, 180, 181],
            incident=[181, 185, 390, 360],
        ),
    )
    baseline_window = QueryWindow(
        start=start, end=start + timedelta(seconds=len(baseline_values) * 30)
    )
    incident_window = QueryWindow(
        start=baseline_window.end,
        end=baseline_window.end + timedelta(seconds=4 * 30),
    )

    first = AnomalyEngine().analyze(
        series,
        baseline_window=baseline_window,
        incident_window=incident_window,
    )
    second = AnomalyEngine().analyze(
        series,
        baseline_window=baseline_window,
        incident_window=incident_window,
    )

    assert [(item.service, item.signal) for item in first.anomalies] == [
        ("payment", SignalName.P95_LATENCY),
        ("checkout", SignalName.P95_LATENCY),
    ]
    assert [item.rank for item in first.anomalies] == [1, 2]
    assert first.anomalies[0].score >= first.anomalies[1].score
    assert first.detectors == (DetectorName.STATISTICAL, DetectorName.ISOLATION_FOREST)
    assert first.evaluated_series == 3
    assert first.evidence_references == tuple(sorted(first.evidence_references))
    assert first.model_dump(exclude={"id", "generated_at"}) == second.model_dump(
        exclude={"id", "generated_at"}
    )


def test_isolation_forest_scores_spike_above_normal_incident_points() -> None:
    start = datetime(2026, 8, 25, 12, tzinfo=UTC)
    latency = metric_series(
        service="payment",
        signal=SignalName.P95_LATENCY,
        start=start,
        baseline=[98, 101, 100, 99, 102, 98, 101, 100, 99, 102, 100, 99],
        incident=[100, 99, 700],
    )
    rate = metric_series(
        service="payment",
        signal=SignalName.REQUEST_RATE,
        start=start,
        baseline=[20, 21, 19, 20, 20, 21, 19, 20, 20, 21, 19, 20],
        incident=[20, 20, 20],
    )

    scores = IsolationForestDetector().score_service(
        {SignalName.P95_LATENCY: latency, SignalName.REQUEST_RATE: rate}
    )

    timestamps = sorted(scores)
    assert scores[timestamps[-1]] > scores[timestamps[0]]
    assert scores == IsolationForestDetector().score_service(
        {SignalName.P95_LATENCY: latency, SignalName.REQUEST_RATE: rate}
    )


def test_isolation_forest_discards_non_finite_aligned_rows() -> None:
    start = datetime(2026, 8, 25, 12, tzinfo=UTC)
    latency = metric_series(
        service="payment",
        signal=SignalName.P95_LATENCY,
        start=start,
        baseline=[98, 101, 100, 99, float("nan"), 98, 101, 100, 99, 102, 100, 99],
        incident=[100, float("nan"), 700],
    )
    rate = metric_series(
        service="payment",
        signal=SignalName.REQUEST_RATE,
        start=start,
        baseline=[20, 21, 19, 20, 20, 21, 19, 20, 20, 21, 19, 20],
        incident=[20, 20, 20],
    )

    scores = IsolationForestDetector().score_service(
        {SignalName.P95_LATENCY: latency, SignalName.REQUEST_RATE: rate}
    )

    assert len(scores) == 2
    assert all(score >= 0 for score in scores.values())

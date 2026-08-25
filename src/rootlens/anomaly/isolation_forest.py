"""Deterministic multivariate Isolation Forest service scoring."""

from __future__ import annotations

import math
from collections.abc import Mapping
from datetime import datetime

import numpy as np
from sklearn.ensemble import IsolationForest  # type: ignore[import-untyped]

from rootlens.anomaly.contracts import MetricSignalSeries, SignalName


class IsolationForestDetector:
    def __init__(
        self,
        *,
        minimum_baseline_samples: int = 8,
        random_state: int = 42,
        estimators: int = 100,
    ) -> None:
        self.minimum_baseline_samples = minimum_baseline_samples
        self._random_state = random_state
        self._estimators = estimators

    def score_service(
        self,
        series_by_signal: Mapping[SignalName, MetricSignalSeries],
    ) -> dict[datetime, float]:
        ordered_signals = sorted(series_by_signal)
        if not ordered_signals:
            return {}
        baseline_rows = _aligned_rows(series_by_signal, ordered_signals, baseline=True)
        incident_rows = _aligned_rows(series_by_signal, ordered_signals, baseline=False)
        if len(baseline_rows) < self.minimum_baseline_samples or not incident_rows:
            return {}

        baseline = np.asarray([row[1] for row in baseline_rows], dtype=np.float64)
        incident = np.asarray([row[1] for row in incident_rows], dtype=np.float64)
        medians = np.median(baseline, axis=0)
        scales = np.median(np.abs(baseline - medians), axis=0) * 1.4826
        standard_deviations = np.std(baseline, axis=0)
        scales = np.where(scales > 0, scales, standard_deviations)
        tolerances = np.maximum(np.abs(medians) * 1e-9, 1e-12)
        varying = scales > tolerances
        if not np.any(varying):
            return {timestamp: 0.0 for timestamp, _ in incident_rows}
        baseline = (baseline[:, varying] - medians[varying]) / scales[varying]
        incident = (incident[:, varying] - medians[varying]) / scales[varying]

        model = IsolationForest(
            n_estimators=self._estimators,
            contamination="auto",
            random_state=self._random_state,
            n_jobs=1,
        )
        model.fit(baseline)
        baseline_abnormality = -model.score_samples(baseline)
        incident_abnormality = -model.score_samples(incident)
        return {
            row[0]: _empirical_percentile(baseline_abnormality, float(score))
            for row, score in zip(incident_rows, incident_abnormality, strict=True)
        }


def _aligned_rows(
    series_by_signal: Mapping[SignalName, MetricSignalSeries],
    signals: list[SignalName],
    *,
    baseline: bool,
) -> list[tuple[datetime, list[float]]]:
    values_by_signal: dict[SignalName, dict[datetime, float]] = {}
    for signal in signals:
        series = series_by_signal[signal]
        samples = series.baseline_samples if baseline else series.incident_samples
        values_by_signal[signal] = {sample.timestamp: sample.value for sample in samples}
    common_timestamps = set.intersection(*(set(values_by_signal[signal]) for signal in signals))
    rows = [
        (timestamp, [values_by_signal[signal][timestamp] for signal in signals])
        for timestamp in sorted(common_timestamps)
    ]
    return [row for row in rows if all(math.isfinite(value) for value in row[1])]


def _empirical_percentile(baseline: np.ndarray, value: float) -> float:
    lower = int(np.count_nonzero(baseline < value))
    equal = int(np.count_nonzero(np.isclose(baseline, value)))
    return (lower + 0.5 * equal) / len(baseline)

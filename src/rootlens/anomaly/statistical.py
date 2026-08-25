"""Interpretable robust statistical anomaly baseline."""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from datetime import datetime

from rootlens.anomaly.contracts import (
    AnomalyDirection,
    BaselineStatistics,
    MetricSignalSeries,
)
from rootlens.telemetry import MetricSample

_ROBUST_SCALE = 1.4826
_SCORE_SATURATION_Z = 6.0


@dataclass(frozen=True)
class StatisticalResult:
    series: MetricSignalSeries
    score: float
    direction: AnomalyDirection
    anomaly_start_time: datetime | None
    peak_timestamp: datetime
    peak_value: float
    max_absolute_robust_z_score: float
    max_absolute_standard_z_score: float
    max_absolute_ewma_z_score: float
    baseline: BaselineStatistics
    scores_by_timestamp: dict[datetime, float]


class StatisticalDetector:
    def __init__(self, *, ewma_alpha: float = 0.3, minimum_baseline_samples: int = 8) -> None:
        if not 0 < ewma_alpha <= 1:
            raise ValueError("ewma_alpha must be in (0, 1]")
        if minimum_baseline_samples < 3:
            raise ValueError("minimum_baseline_samples must be at least 3")
        self._ewma_alpha = ewma_alpha
        self.minimum_baseline_samples = minimum_baseline_samples

    def score(self, series: MetricSignalSeries) -> StatisticalResult:
        baseline = _finite_values(series.baseline_samples)
        incident = tuple(
            sample
            for sample in sorted(series.incident_samples, key=lambda item: item.timestamp)
            if math.isfinite(sample.value)
        )
        if len(baseline) < self.minimum_baseline_samples:
            raise ValueError(
                f"requires at least {self.minimum_baseline_samples} finite baseline samples"
            )
        if not incident:
            raise ValueError("requires at least one finite incident sample")

        mean = statistics.fmean(baseline)
        standard_deviation = statistics.pstdev(baseline)
        median = statistics.median(baseline)
        mad = statistics.median(abs(value - median) for value in baseline)
        robust_scale = _ROBUST_SCALE * mad
        fallback_scale = robust_scale if robust_scale > 0 else standard_deviation
        ewma = baseline[0]
        for value in baseline[1:]:
            bounded_value = _clip_for_baseline_ewma(
                value,
                center=median,
                scale=fallback_scale,
            )
            ewma = self._ewma_alpha * bounded_value + (1 - self._ewma_alpha) * ewma
        final_baseline_ewma = ewma

        scored: list[tuple[datetime, float, float, float, float, float]] = []
        for sample in incident:
            robust_z = _standardized(sample.value, median, robust_scale, standard_deviation)
            standard_z = _standardized(
                sample.value,
                mean,
                standard_deviation,
                robust_scale,
            )
            ewma_z = _standardized(sample.value, ewma, fallback_scale, standard_deviation)
            magnitude = max(abs(robust_z), abs(standard_z), abs(ewma_z))
            score = min(magnitude / _SCORE_SATURATION_Z, 1.0)
            scored.append((sample.timestamp, sample.value, score, robust_z, standard_z, ewma_z))
            ewma = self._ewma_alpha * sample.value + (1 - self._ewma_alpha) * ewma

        peak = max(scored, key=lambda item: (item[2], -item[0].timestamp()))
        anomalous = [item for item in scored if item[2] >= 0.5]
        start_time = anomalous[0][0] if anomalous else None
        direction = AnomalyDirection.HIGH if peak[1] >= median else AnomalyDirection.LOW
        return StatisticalResult(
            series=series,
            score=peak[2],
            direction=direction,
            anomaly_start_time=start_time,
            peak_timestamp=peak[0],
            peak_value=peak[1],
            max_absolute_robust_z_score=max(abs(item[3]) for item in scored),
            max_absolute_standard_z_score=max(abs(item[4]) for item in scored),
            max_absolute_ewma_z_score=max(abs(item[5]) for item in scored),
            baseline=BaselineStatistics(
                sample_count=len(baseline),
                mean=mean,
                standard_deviation=standard_deviation,
                median=median,
                median_absolute_deviation=mad,
                final_ewma=final_baseline_ewma,
            ),
            scores_by_timestamp={item[0]: item[2] for item in scored},
        )


def _finite_values(samples: tuple[MetricSample, ...]) -> tuple[float, ...]:
    values = tuple(
        sample.value
        for sample in sorted(samples, key=lambda item: item.timestamp)
        if math.isfinite(sample.value)
    )
    return values


def _standardized(value: float, center: float, scale: float, fallback: float) -> float:
    difference = value - center
    tolerance = max(abs(center) * 1e-9, 1e-12)
    if abs(difference) <= tolerance:
        return 0.0
    usable_scale = scale if scale > tolerance else fallback
    if usable_scale > tolerance:
        return difference / usable_scale
    return math.copysign(_SCORE_SATURATION_Z, difference)


def _clip_for_baseline_ewma(value: float, *, center: float, scale: float) -> float:
    tolerance = max(abs(center) * 1e-9, 1e-12)
    if scale <= tolerance:
        return center if abs(value - center) <= tolerance else value
    radius = 3 * scale
    return min(max(value, center - radius), center + radius)

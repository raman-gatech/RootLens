"""Combine statistical attribution and service-level Isolation Forest scoring."""

from collections import defaultdict
from datetime import datetime

from rootlens.anomaly.contracts import (
    AnomalyAnalysisSnapshot,
    DetectorName,
    MetricSignalSeries,
    RankedAnomaly,
    SignalName,
)
from rootlens.anomaly.isolation_forest import IsolationForestDetector
from rootlens.anomaly.statistical import StatisticalDetector, StatisticalResult
from rootlens.telemetry import QueryWindow


class AnomalyEngine:
    def __init__(
        self,
        *,
        statistical: StatisticalDetector | None = None,
        isolation_forest: IsolationForestDetector | None = None,
    ) -> None:
        self._statistical = statistical or StatisticalDetector()
        self._isolation_forest = isolation_forest or IsolationForestDetector()

    def analyze(
        self,
        series: tuple[MetricSignalSeries, ...],
        *,
        baseline_window: QueryWindow,
        incident_window: QueryWindow,
        minimum_score: float = 0.5,
    ) -> AnomalyAnalysisSnapshot:
        statistical_results: list[StatisticalResult] = []
        warnings: list[str] = []
        for item in sorted(series, key=lambda value: (value.service, value.signal.value)):
            try:
                statistical_results.append(self._statistical.score(item))
            except ValueError as error:
                warnings.append(f"{item.service}/{item.signal.value}: {error}")

        # Isolation Forest is a second-stage scorer. Running one model for every
        # healthy service made the normal (no-anomaly) path scale with the full
        # topology even though those scores could never affect the output. Only
        # services admitted by the statistical screen can produce a ranked
        # anomaly, so restrict multivariate scoring to that candidate set.
        candidate_results = tuple(
            result for result in statistical_results if result.anomaly_start_time is not None
        )
        candidate_services = {result.series.service for result in candidate_results}
        by_service: dict[str, dict[SignalName, MetricSignalSeries]] = defaultdict(dict)
        for result in statistical_results:
            if result.series.service in candidate_services:
                by_service[result.series.service][result.series.signal] = result.series
        forest_scores = {
            service: self._isolation_forest.score_service(service_series)
            for service, service_series in by_service.items()
        }

        unranked: list[RankedAnomaly] = []
        for result in statistical_results:
            if result.anomaly_start_time is None:
                continue
            forest_score = _score_at_or_nearest(
                forest_scores[result.series.service], result.peak_timestamp
            )
            combined_score = (
                result.score if forest_score is None else 0.7 * result.score + 0.3 * forest_score
            )
            if combined_score < minimum_score:
                continue
            unranked.append(
                RankedAnomaly(
                    rank=1,
                    service=result.series.service,
                    signal=result.series.signal,
                    score=combined_score,
                    statistical_score=result.score,
                    isolation_forest_score=forest_score,
                    direction=result.direction,
                    anomaly_start_time=result.anomaly_start_time,
                    peak_timestamp=result.peak_timestamp,
                    peak_value=result.peak_value,
                    max_absolute_robust_z_score=result.max_absolute_robust_z_score,
                    max_absolute_standard_z_score=result.max_absolute_standard_z_score,
                    max_absolute_ewma_z_score=result.max_absolute_ewma_z_score,
                    baseline=result.baseline,
                    incident_sample_count=len(result.series.incident_samples),
                    evidence_references=result.series.evidence_references,
                )
            )

        ordered = sorted(
            unranked,
            key=lambda anomaly: (
                -anomaly.score,
                anomaly.anomaly_start_time,
                anomaly.service,
                anomaly.signal.value,
            ),
        )
        ranked = tuple(
            anomaly.model_copy(update={"rank": rank})
            for rank, anomaly in enumerate(ordered, start=1)
        )
        evidence_references = tuple(
            sorted({reference for item in series for reference in item.evidence_references})
        )
        used_forest = any(scores for scores in forest_scores.values())
        detectors: tuple[DetectorName, ...] = (DetectorName.STATISTICAL,)
        if used_forest:
            detectors += (DetectorName.ISOLATION_FOREST,)
        elif candidate_results:
            warnings.append(
                "Isolation Forest skipped because aligned baseline data was insufficient"
            )
        return AnomalyAnalysisSnapshot(
            baseline_window=baseline_window,
            incident_window=incident_window,
            detectors=detectors,
            evaluated_series=len(statistical_results),
            minimum_score=minimum_score,
            anomalies=ranked,
            evidence_references=evidence_references,
            warnings=tuple(warnings),
        )


def _score_at_or_nearest(scores: dict[datetime, float], timestamp: datetime) -> float | None:
    if not scores:
        return None
    if timestamp in scores:
        return scores[timestamp]
    nearest = min(scores, key=lambda item: abs((item - timestamp).total_seconds()))
    return scores[nearest]

"""Collect provenance-bearing Prometheus features and run anomaly analysis."""

import asyncio
from collections.abc import Iterable, Sequence

from rootlens.anomaly.catalog import SIGNAL_CATALOG, SignalDefinition
from rootlens.anomaly.contracts import (
    AnomalyAnalysisSnapshot,
    MetricSignalSeries,
    SignalName,
)
from rootlens.anomaly.engine import AnomalyEngine
from rootlens.anomaly.errors import AnomalyAnalysisError
from rootlens.anomaly.repository import AnomalyRepository
from rootlens.telemetry import MetricSeries, QueryWindow, TelemetryEnvelope
from rootlens.telemetry.prometheus import PrometheusClient


class AnomalyAnalysisService:
    def __init__(
        self,
        *,
        prometheus: PrometheusClient,
        repository: AnomalyRepository,
        engine: AnomalyEngine | None = None,
    ) -> None:
        self._prometheus = prometheus
        self._repository = repository
        self._engine = engine or AnomalyEngine()

    async def analyze(
        self,
        *,
        baseline_window: QueryWindow,
        incident_window: QueryWindow,
        signals: Sequence[SignalName],
        step_seconds: int,
        minimum_score: float,
    ) -> AnomalyAnalysisSnapshot:
        definitions = tuple(SIGNAL_CATALOG[signal] for signal in signals)
        responses = await asyncio.gather(
            *(
                self._prometheus.query_range(
                    definition.promql,
                    window,
                    step_seconds=step_seconds,
                )
                for definition in definitions
                for window in (baseline_window, incident_window)
            )
        )
        collected, warnings = _collect_series(definitions, responses)
        if not collected:
            raise AnomalyAnalysisError(
                "Prometheus returned no service/signal series shared by both windows"
            )
        snapshot = await asyncio.to_thread(
            self._engine.analyze,
            collected,
            baseline_window=baseline_window,
            incident_window=incident_window,
            minimum_score=minimum_score,
        )
        if warnings:
            snapshot = snapshot.model_copy(
                update={"warnings": tuple((*snapshot.warnings, *warnings))}
            )
        await self._repository.save(snapshot)
        return snapshot

    async def latest(self) -> AnomalyAnalysisSnapshot | None:
        return await self._repository.latest()


def _collect_series(
    definitions: Sequence[SignalDefinition],
    responses: Sequence[TelemetryEnvelope[list[MetricSeries]]],
) -> tuple[tuple[MetricSignalSeries, ...], tuple[str, ...]]:
    collected: list[MetricSignalSeries] = []
    warnings: list[str] = []
    for index, definition in enumerate(definitions):
        baseline = responses[index * 2]
        incident = responses[index * 2 + 1]
        baseline_by_service = _by_service(baseline.data, definition.service_label)
        incident_by_service = _by_service(incident.data, definition.service_label)
        common_services = sorted(set(baseline_by_service) & set(incident_by_service))
        missing = sorted(set(baseline_by_service) ^ set(incident_by_service))
        if missing:
            warnings.append(
                f"{definition.signal.value}: skipped services absent from one window: "
                + ", ".join(missing)
            )
        for service in common_services:
            collected.append(
                MetricSignalSeries(
                    service=service,
                    signal=definition.signal,
                    baseline_samples=tuple(baseline_by_service[service].samples),
                    incident_samples=tuple(incident_by_service[service].samples),
                    evidence_references=(
                        baseline.provenance.reference,
                        incident.provenance.reference,
                    ),
                )
            )
    return tuple(collected), tuple(warnings)


def _by_service(series: Iterable[MetricSeries], label: str) -> dict[str, MetricSeries]:
    result: dict[str, MetricSeries] = {}
    for item in series:
        service = item.labels.get(label)
        if service:
            result[service] = item
    return result

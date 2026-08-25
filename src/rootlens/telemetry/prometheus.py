"""Prometheus HTTP API client and PromQL result normalization."""

from datetime import UTC, datetime

import httpx

from rootlens.telemetry.contracts import (
    MetricSample,
    MetricSeries,
    QueryProvenance,
    QueryWindow,
    TelemetryEnvelope,
    TelemetrySource,
)
from rootlens.telemetry.http import AsyncTelemetryHttpClient
from rootlens.telemetry.parsing import invalid, mapping, sequence, string_map, text


class PrometheusClient(AsyncTelemetryHttpClient):
    def __init__(
        self,
        base_url: str,
        *,
        timeout_seconds: float = 10.0,
        max_retries: int = 2,
        max_response_bytes: int = 10_485_760,
        max_concurrency: int = 8,
        transport: httpx.AsyncBaseTransport | None = None,
        retry_backoff_seconds: float = 0.1,
    ) -> None:
        super().__init__(
            source=TelemetrySource.PROMETHEUS,
            base_url=base_url,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
            max_response_bytes=max_response_bytes,
            max_concurrency=max_concurrency,
            transport=transport,
            retry_backoff_seconds=retry_backoff_seconds,
        )

    async def query(
        self,
        promql: str,
        *,
        evaluation_time: datetime | None = None,
    ) -> TelemetryEnvelope[list[MetricSeries]]:
        evaluated_at = evaluation_time or datetime.now(UTC)
        _require_aware(evaluated_at)
        params = {"query": promql, "time": _unix_seconds(evaluated_at)}
        payload = await self.get_json("/api/v1/query", params=params)
        series = _parse_query_response(payload)
        return TelemetryEnvelope(
            provenance=QueryProvenance.create(
                source=self.source,
                query=promql,
                parameters=params,
            ),
            data=series,
        )

    async def query_range(
        self,
        promql: str,
        window: QueryWindow,
        *,
        step_seconds: int = 30,
    ) -> TelemetryEnvelope[list[MetricSeries]]:
        if step_seconds <= 0:
            raise ValueError("step_seconds must be positive")
        params = {
            "query": promql,
            "start": _unix_seconds(window.start),
            "end": _unix_seconds(window.end),
            "step": str(step_seconds),
        }
        payload = await self.get_json("/api/v1/query_range", params=params)
        series = _parse_query_response(payload)
        return TelemetryEnvelope(
            provenance=QueryProvenance.create(
                source=self.source,
                query=promql,
                parameters=params,
                window=window,
            ),
            data=series,
        )


def _parse_query_response(payload: object) -> list[MetricSeries]:
    root = mapping(payload, TelemetrySource.PROMETHEUS, "response")
    if root.get("status") != "success":
        raise invalid(TelemetrySource.PROMETHEUS, "Prometheus query was not successful")
    data = mapping(root.get("data"), TelemetrySource.PROMETHEUS, "data")
    result_type = text(data.get("resultType"), TelemetrySource.PROMETHEUS, "resultType")
    raw_result = data.get("result")
    if result_type in {"scalar", "string"}:
        return [MetricSeries(labels={}, samples=[_sample(raw_result, "result")])]
    if result_type not in {"vector", "matrix"}:
        raise invalid(TelemetrySource.PROMETHEUS, f"unsupported result type: {result_type}")

    parsed: list[MetricSeries] = []
    for index, raw_series in enumerate(sequence(raw_result, TelemetrySource.PROMETHEUS, "result")):
        item = mapping(raw_series, TelemetrySource.PROMETHEUS, f"result[{index}]")
        labels = string_map(item.get("metric"))
        if result_type == "vector":
            samples = [_sample(item.get("value"), f"result[{index}].value")]
        else:
            samples = [
                _sample(value, f"result[{index}].values[{sample_index}]")
                for sample_index, value in enumerate(
                    sequence(
                        item.get("values"),
                        TelemetrySource.PROMETHEUS,
                        f"result[{index}].values",
                    )
                )
            ]
        parsed.append(MetricSeries(labels=labels, samples=samples))
    return parsed


def _sample(value: object, field: str) -> MetricSample:
    pair = sequence(value, TelemetrySource.PROMETHEUS, field)
    if len(pair) != 2:
        raise invalid(TelemetrySource.PROMETHEUS, f"{field} must contain timestamp and value")
    try:
        timestamp = datetime.fromtimestamp(float(str(pair[0])), tz=UTC)
        number = float(str(pair[1]))
    except (TypeError, ValueError, OverflowError) as exc:
        raise invalid(TelemetrySource.PROMETHEUS, f"{field} contains invalid sample data") from exc
    return MetricSample(timestamp=timestamp, value=number)


def _unix_seconds(value: datetime) -> str:
    return f"{value.timestamp():.6f}"


def _require_aware(value: datetime) -> None:
    if value.tzinfo is None:
        raise ValueError("evaluation_time must be timezone-aware")

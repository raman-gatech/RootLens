"""Tempo HTTP API client and OTLP trace normalization."""

import base64
import re
from datetime import UTC, datetime

import httpx

from rootlens.telemetry.contracts import (
    QueryProvenance,
    QueryWindow,
    SpanRecord,
    TelemetryEnvelope,
    TelemetrySource,
    TraceSummary,
)
from rootlens.telemetry.http import AsyncTelemetryHttpClient
from rootlens.telemetry.parsing import invalid, mapping, optional_text, sequence, text

_TRACE_ID_PATTERN = re.compile(r"^[0-9a-fA-F]{16,32}$")


class TempoClient(AsyncTelemetryHttpClient):
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
            source=TelemetrySource.TEMPO,
            base_url=base_url,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
            max_response_bytes=max_response_bytes,
            max_concurrency=max_concurrency,
            transport=transport,
            retry_backoff_seconds=retry_backoff_seconds,
        )

    async def search_traces(
        self,
        traceql: str,
        window: QueryWindow,
        *,
        limit: int = 20,
    ) -> TelemetryEnvelope[list[TraceSummary]]:
        if limit <= 0:
            raise ValueError("limit must be positive")
        params = {
            "q": traceql,
            "start": str(int(window.start.timestamp())),
            "end": str(int(window.end.timestamp())),
            "limit": str(limit),
        }
        payload = await self.get_json("/api/search", params=params)
        summaries = _parse_search_response(payload)
        return TelemetryEnvelope(
            provenance=QueryProvenance.create(
                source=self.source,
                query=traceql,
                parameters=params,
                window=window,
            ),
            data=summaries,
        )

    async def get_trace(self, trace_id: str) -> TelemetryEnvelope[list[SpanRecord]]:
        if not _TRACE_ID_PATTERN.fullmatch(trace_id):
            raise ValueError("trace_id must contain 16 to 32 hexadecimal characters")
        normalized_id = trace_id.lower()
        path = f"/api/traces/{normalized_id}"
        payload = await self.get_json(path, params={})
        spans = _parse_trace_response(payload)
        return TelemetryEnvelope(
            provenance=QueryProvenance.create(
                source=self.source,
                query=path,
                parameters={"trace_id": normalized_id},
            ),
            data=spans,
        )


def _parse_search_response(payload: object) -> list[TraceSummary]:
    root = mapping(payload, TelemetrySource.TEMPO, "response")
    summaries: list[TraceSummary] = []
    for index, raw_trace in enumerate(
        sequence(root.get("traces"), TelemetrySource.TEMPO, "traces")
    ):
        item = mapping(raw_trace, TelemetrySource.TEMPO, f"traces[{index}]")
        trace_id = text(item.get("traceID"), TelemetrySource.TEMPO, "traceID")
        start_time = _optional_unix_nanoseconds(item.get("startTimeUnixNano"))
        duration_ms = _optional_float(item.get("durationMs"))
        summaries.append(
            TraceSummary(
                trace_id=trace_id,
                root_service_name=optional_text(item.get("rootServiceName")),
                root_trace_name=optional_text(item.get("rootTraceName")),
                start_time=start_time,
                duration_seconds=duration_ms / 1_000 if duration_ms is not None else None,
            )
        )
    return summaries


def _parse_trace_response(payload: object) -> list[SpanRecord]:
    root = mapping(payload, TelemetrySource.TEMPO, "response")
    spans: list[SpanRecord] = []
    for batch_index, raw_batch in enumerate(
        sequence(root.get("batches"), TelemetrySource.TEMPO, "batches")
    ):
        batch = mapping(raw_batch, TelemetrySource.TEMPO, f"batches[{batch_index}]")
        resource = mapping(
            batch.get("resource"), TelemetrySource.TEMPO, f"batches[{batch_index}].resource"
        )
        resource_attributes = _attributes(resource.get("attributes"))
        service_value = resource_attributes.get("service.name")
        service_name = service_value if isinstance(service_value, str) else None
        for scope_index, raw_scope in enumerate(
            sequence(
                batch.get("scopeSpans"),
                TelemetrySource.TEMPO,
                f"batches[{batch_index}].scopeSpans",
            )
        ):
            scope = mapping(
                raw_scope,
                TelemetrySource.TEMPO,
                f"batches[{batch_index}].scopeSpans[{scope_index}]",
            )
            for span_index, raw_span in enumerate(
                sequence(scope.get("spans"), TelemetrySource.TEMPO, "spans")
            ):
                span = mapping(raw_span, TelemetrySource.TEMPO, f"spans[{span_index}]")
                trace_id = _otlp_id(span.get("traceId"), "traceId")
                span_id = _otlp_id(span.get("spanId"), "spanId")
                parent_raw = span.get("parentSpanId")
                parent_id = _otlp_id(parent_raw, "parentSpanId") if parent_raw else None
                start = _required_unix_nanoseconds(span.get("startTimeUnixNano"), "start")
                end = _required_unix_nanoseconds(span.get("endTimeUnixNano"), "end")
                status = span.get("status")
                status_code = None
                if isinstance(status, dict):
                    status_code = optional_text(status.get("code"))
                spans.append(
                    SpanRecord(
                        trace_id=trace_id,
                        span_id=span_id,
                        parent_span_id=parent_id,
                        service_name=service_name,
                        name=text(span.get("name"), TelemetrySource.TEMPO, "span.name"),
                        kind=optional_text(span.get("kind")),
                        start_time=start,
                        end_time=end,
                        status_code=status_code,
                        attributes={**resource_attributes, **_attributes(span.get("attributes"))},
                    )
                )
    return spans


def _attributes(value: object) -> dict[str, str | int | float | bool]:
    if value is None:
        return {}
    parsed: dict[str, str | int | float | bool] = {}
    for raw_attribute in sequence(value, TelemetrySource.TEMPO, "attributes"):
        attribute = mapping(raw_attribute, TelemetrySource.TEMPO, "attribute")
        key = optional_text(attribute.get("key"))
        raw_value = attribute.get("value")
        if key is None or not isinstance(raw_value, dict):
            continue
        for value_key in ("stringValue", "intValue", "doubleValue", "boolValue"):
            scalar = raw_value.get(value_key)
            if isinstance(scalar, str | int | float | bool):
                parsed[key] = scalar
                break
    return parsed


def _otlp_id(value: object, field: str) -> str:
    encoded = text(value, TelemetrySource.TEMPO, field)
    try:
        decoded = base64.b64decode(encoded, validate=True)
    except ValueError as exc:
        raise invalid(TelemetrySource.TEMPO, f"{field} is not valid base64") from exc
    if not decoded:
        raise invalid(TelemetrySource.TEMPO, f"{field} is empty")
    return decoded.hex()


def _required_unix_nanoseconds(value: object, field: str) -> datetime:
    parsed = _optional_unix_nanoseconds(value)
    if parsed is None:
        raise invalid(TelemetrySource.TEMPO, f"{field} is not a Unix nanosecond timestamp")
    return parsed


def _optional_unix_nanoseconds(value: object) -> datetime | None:
    try:
        return datetime.fromtimestamp(int(str(value)) / 1_000_000_000, tz=UTC)
    except (TypeError, ValueError, OverflowError):
        return None


def _optional_float(value: object) -> float | None:
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None

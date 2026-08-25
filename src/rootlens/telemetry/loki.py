"""Loki HTTP API client and LogQL stream normalization."""

from datetime import UTC, datetime

import httpx

from rootlens.telemetry.contracts import (
    LogEntry,
    LogStream,
    QueryProvenance,
    QueryWindow,
    TelemetryEnvelope,
    TelemetrySource,
)
from rootlens.telemetry.http import AsyncTelemetryHttpClient
from rootlens.telemetry.parsing import invalid, mapping, sequence, string_map, text


class LokiClient(AsyncTelemetryHttpClient):
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
            source=TelemetrySource.LOKI,
            base_url=base_url,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
            max_response_bytes=max_response_bytes,
            max_concurrency=max_concurrency,
            transport=transport,
            retry_backoff_seconds=retry_backoff_seconds,
        )

    async def query_range(
        self,
        logql: str,
        window: QueryWindow,
        *,
        limit: int = 1_000,
        direction: str = "backward",
    ) -> TelemetryEnvelope[list[LogStream]]:
        if limit <= 0:
            raise ValueError("limit must be positive")
        if direction not in {"forward", "backward"}:
            raise ValueError("direction must be forward or backward")
        params = {
            "query": logql,
            "start": _unix_nanoseconds(window.start),
            "end": _unix_nanoseconds(window.end),
            "limit": str(limit),
            "direction": direction,
        }
        payload = await self.get_json("/loki/api/v1/query_range", params=params)
        streams = _parse_stream_response(payload)
        return TelemetryEnvelope(
            provenance=QueryProvenance.create(
                source=self.source,
                query=logql,
                parameters=params,
                window=window,
            ),
            data=streams,
        )


def _parse_stream_response(payload: object) -> list[LogStream]:
    root = mapping(payload, TelemetrySource.LOKI, "response")
    if root.get("status") != "success":
        raise invalid(TelemetrySource.LOKI, "Loki query was not successful")
    data = mapping(root.get("data"), TelemetrySource.LOKI, "data")
    result_type = text(data.get("resultType"), TelemetrySource.LOKI, "resultType")
    if result_type != "streams":
        raise invalid(TelemetrySource.LOKI, f"expected streams result, received {result_type}")

    streams: list[LogStream] = []
    for index, raw_stream in enumerate(
        sequence(data.get("result"), TelemetrySource.LOKI, "result")
    ):
        item = mapping(raw_stream, TelemetrySource.LOKI, f"result[{index}]")
        entries: list[LogEntry] = []
        for entry_index, raw_entry in enumerate(
            sequence(item.get("values"), TelemetrySource.LOKI, f"result[{index}].values")
        ):
            pair = sequence(
                raw_entry,
                TelemetrySource.LOKI,
                f"result[{index}].values[{entry_index}]",
            )
            if len(pair) != 2:
                raise invalid(TelemetrySource.LOKI, "log entry must contain timestamp and line")
            try:
                timestamp = datetime.fromtimestamp(int(str(pair[0])) / 1_000_000_000, tz=UTC)
            except (TypeError, ValueError, OverflowError) as exc:
                raise invalid(TelemetrySource.LOKI, "log entry timestamp is invalid") from exc
            line = text(pair[1], TelemetrySource.LOKI, "log line")
            entries.append(LogEntry(timestamp=timestamp, line=line))
        streams.append(LogStream(labels=string_map(item.get("stream")), entries=entries))
    return streams


def _unix_nanoseconds(value: datetime) -> str:
    return str(int(value.timestamp() * 1_000_000_000))

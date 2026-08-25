"""Tests for retry and safety boundaries in the shared HTTP transport."""

import httpx
import pytest

from rootlens.telemetry import TelemetryErrorCode, TelemetryQueryError, TelemetrySource
from rootlens.telemetry.http import AsyncTelemetryHttpClient


@pytest.mark.asyncio
async def test_retries_retryable_status_then_returns_json() -> None:
    attempts = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(503)
        return httpx.Response(200, json={"ok": True})

    client = AsyncTelemetryHttpClient(
        source=TelemetrySource.PROMETHEUS,
        base_url="http://prometheus.test",
        max_retries=1,
        retry_backoff_seconds=0,
        transport=httpx.MockTransport(handler),
    )
    try:
        result = await client.get_json("/query", params={})
    finally:
        await client.aclose()

    assert result == {"ok": True}
    assert attempts == 2


@pytest.mark.asyncio
async def test_does_not_retry_non_retryable_status() -> None:
    attempts = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(400, text="secret backend details")

    client = AsyncTelemetryHttpClient(
        source=TelemetrySource.LOKI,
        base_url="http://loki.test",
        max_retries=2,
        retry_backoff_seconds=0,
        transport=httpx.MockTransport(handler),
    )
    try:
        with pytest.raises(TelemetryQueryError) as captured:
            await client.get_json("/query", params={})
    finally:
        await client.aclose()

    assert captured.value.code is TelemetryErrorCode.HTTP_STATUS
    assert captured.value.status_code == 400
    assert captured.value.retryable is False
    assert "secret backend details" not in str(captured.value)
    assert attempts == 1


@pytest.mark.asyncio
async def test_rejects_oversized_response() -> None:
    client = AsyncTelemetryHttpClient(
        source=TelemetrySource.TEMPO,
        base_url="http://tempo.test",
        max_response_bytes=5,
        transport=httpx.MockTransport(lambda _: httpx.Response(200, content=b"123456")),
    )
    try:
        with pytest.raises(TelemetryQueryError) as captured:
            await client.get_json("/trace", params={})
    finally:
        await client.aclose()

    assert captured.value.code is TelemetryErrorCode.RESPONSE_TOO_LARGE

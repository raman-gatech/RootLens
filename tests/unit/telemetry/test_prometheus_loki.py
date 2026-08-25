"""Backend contract tests for Prometheus and Loki."""

from datetime import UTC, datetime, timedelta

import httpx
import pytest

from rootlens.telemetry import QueryWindow, TelemetrySource
from rootlens.telemetry.loki import LokiClient
from rootlens.telemetry.prometheus import PrometheusClient


@pytest.mark.asyncio
async def test_prometheus_vector_is_normalized_with_provenance() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/query"
        assert request.url.params["query"] == "up"
        return httpx.Response(
            200,
            json={
                "status": "success",
                "data": {
                    "resultType": "vector",
                    "result": [{"metric": {"job": "demo"}, "value": [10, "1"]}],
                },
            },
        )

    client = PrometheusClient("http://prometheus.test", transport=httpx.MockTransport(handler))
    try:
        result = await client.query("up", evaluation_time=datetime(2026, 8, 24, tzinfo=UTC))
    finally:
        await client.aclose()

    assert result.provenance.source is TelemetrySource.PROMETHEUS
    assert result.provenance.query == "up"
    assert result.data[0].labels == {"job": "demo"}
    assert result.data[0].samples[0].value == 1


@pytest.mark.asyncio
async def test_loki_streams_are_normalized_with_window() -> None:
    now = datetime(2026, 8, 24, tzinfo=UTC)
    window = QueryWindow(start=now - timedelta(minutes=5), end=now)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/loki/api/v1/query_range"
        assert request.url.params["query"] == '{service_name="checkout"}'
        return httpx.Response(
            200,
            json={
                "status": "success",
                "data": {
                    "resultType": "streams",
                    "result": [
                        {
                            "stream": {"service_name": "checkout"},
                            "values": [["1787587200000000000", "request completed"]],
                        }
                    ],
                },
            },
        )

    client = LokiClient("http://loki.test", transport=httpx.MockTransport(handler))
    try:
        result = await client.query_range('{service_name="checkout"}', window)
    finally:
        await client.aclose()

    assert result.provenance.source is TelemetrySource.LOKI
    assert result.provenance.window == window
    assert result.data[0].labels["service_name"] == "checkout"
    assert result.data[0].entries[0].line == "request completed"

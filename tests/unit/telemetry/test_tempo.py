"""Backend contract tests for Tempo search and trace retrieval."""

import base64
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from rootlens.telemetry import QueryWindow, TelemetrySource
from rootlens.telemetry.tempo import TempoClient


@pytest.mark.asyncio
async def test_tempo_search_and_trace_are_normalized() -> None:
    trace_bytes = bytes.fromhex("00112233445566778899aabbccddeeff")
    span_bytes = bytes.fromhex("0011223344556677")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/search":
            return httpx.Response(
                200,
                json={
                    "traces": [
                        {
                            "traceID": trace_bytes.hex(),
                            "rootServiceName": "checkout",
                            "rootTraceName": "POST /checkout",
                            "startTimeUnixNano": "1787587200000000000",
                            "durationMs": 25,
                        }
                    ]
                },
            )
        assert request.url.path == f"/api/traces/{trace_bytes.hex()}"
        return httpx.Response(
            200,
            json={
                "batches": [
                    {
                        "resource": {
                            "attributes": [
                                {"key": "service.name", "value": {"stringValue": "checkout"}}
                            ]
                        },
                        "scopeSpans": [
                            {
                                "spans": [
                                    {
                                        "traceId": base64.b64encode(trace_bytes).decode(),
                                        "spanId": base64.b64encode(span_bytes).decode(),
                                        "name": "POST /checkout",
                                        "kind": "SPAN_KIND_SERVER",
                                        "startTimeUnixNano": "1787587200000000000",
                                        "endTimeUnixNano": "1787587200025000000",
                                        "attributes": [],
                                        "status": {"code": "STATUS_CODE_OK"},
                                    }
                                ]
                            }
                        ],
                    }
                ]
            },
        )

    client = TempoClient("http://tempo.test", transport=httpx.MockTransport(handler))
    now = datetime(2026, 8, 24, tzinfo=UTC)
    try:
        search = await client.search_traces(
            "{}", QueryWindow(start=now - timedelta(hours=1), end=now), limit=1
        )
        trace = await client.get_trace(search.data[0].trace_id)
    finally:
        await client.aclose()

    assert search.provenance.source is TelemetrySource.TEMPO
    assert search.data[0].root_service_name == "checkout"
    assert trace.data[0].trace_id == trace_bytes.hex()
    assert trace.data[0].span_id == span_bytes.hex()
    assert trace.data[0].service_name == "checkout"

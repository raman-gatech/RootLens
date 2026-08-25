#!/usr/bin/env python3
"""Exercise Milestone 2 clients against the running local observability stack."""

import asyncio
import sys
from datetime import UTC, datetime, timedelta

from rootlens.config import Settings
from rootlens.telemetry import QueryWindow, TelemetryGateway


async def verify() -> None:
    now = datetime.now(UTC)
    window = QueryWindow(start=now - timedelta(hours=1), end=now)

    async with TelemetryGateway.from_settings(Settings(telemetry_enabled=False)) as gateway:
        metrics = await gateway.prometheus.query("up", evaluation_time=now)
        if not metrics.data:
            raise RuntimeError("Prometheus returned no series for up")
        print(f"PASS Prometheus client ({metrics.provenance.reference})")

        logs = await gateway.loki.query_range('{service_name=~".+"}', window, limit=10)
        if not any(stream.entries for stream in logs.data):
            raise RuntimeError("Loki returned no log entries in the last hour")
        print(f"PASS Loki client ({logs.provenance.reference})")

        traces = await gateway.tempo.search_traces("{}", window, limit=1)
        if not traces.data:
            raise RuntimeError("Tempo returned no traces in the last hour")
        print(f"PASS Tempo search client ({traces.provenance.reference})")

        spans = await gateway.tempo.get_trace(traces.data[0].trace_id)
        if not spans.data:
            raise RuntimeError("Tempo returned a trace with no spans")
        print(f"PASS Tempo trace client ({spans.provenance.reference})")


def main() -> int:
    try:
        asyncio.run(verify())
    except Exception as error:
        print(f"FAIL Milestone 2 gateway verification: {error}", file=sys.stderr)
        return 1
    print("Milestone 2 telemetry gateway verification passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Verify the Milestone 1 local stack using public HTTP endpoints."""

from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen


@dataclass(frozen=True)
class Check:
    name: str
    url: str
    predicate: object | None = None


def read_json(url: str, timeout: float = 5.0) -> dict[str, Any]:
    with urlopen(url, timeout=timeout) as response:
        return json.load(response)


def wait_for_json(check: Check, timeout: float = 180.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last_error = "no response"
    while time.monotonic() < deadline:
        try:
            payload = read_json(check.url)
            if check.predicate is None or check.predicate(payload):  # type: ignore[operator]
                print(f"PASS {check.name}")
                return payload
            last_error = f"unexpected payload: {payload}"
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as error:
            last_error = str(error)
        time.sleep(2)
    raise RuntimeError(f"{check.name} failed: {last_error}")


def prometheus_query(query: str) -> str:
    return "http://localhost:9090/api/v1/query?" + urlencode({"query": query})


def has_prometheus_results(payload: dict[str, Any]) -> bool:
    return payload.get("status") == "success" and bool(payload.get("data", {}).get("result"))


def main() -> int:
    checks = [
        Check(
            "RootLens API readiness",
            "http://localhost:8000/health/ready",
            lambda body: body.get("status") == "ready",
        ),
        Check(
            "Grafana readiness",
            "http://localhost:3001/api/health",
            lambda body: body.get("database") == "ok",
        ),
        Check(
            "Prometheus ingestion",
            prometheus_query("up"),
            has_prometheus_results,
        ),
        Check(
            "OpenTelemetry Demo metrics",
            prometheus_query('count({service_namespace="opentelemetry-demo"})'),
            has_prometheus_results,
        ),
        Check(
            "Tempo trace search",
            "http://localhost:3200/api/search?limit=1",
            lambda body: bool(body.get("traces")),
        ),
        Check(
            "Loki log ingestion",
            "http://localhost:3100/loki/api/v1/labels",
            lambda body: body.get("status") == "success" and bool(body.get("data")),
        ),
        Check(
            "Tempo service graph metrics",
            prometheus_query("traces_service_graph_request_total"),
            has_prometheus_results,
        ),
    ]

    try:
        for check in checks:
            wait_for_json(check)
    except RuntimeError as error:
        print(f"FAIL {error}", file=sys.stderr)
        return 1

    print("Milestone 1 stack verification passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

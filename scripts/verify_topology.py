#!/usr/bin/env python3
"""Reconstruct, persist, and traverse a live service graph through the API."""

import sys
from datetime import UTC, datetime, timedelta

import httpx


def verify() -> None:
    now = datetime.now(UTC)
    payload = {
        "start": (now - timedelta(minutes=15)).isoformat(),
        "end": now.isoformat(),
        "traceql": "{}",
        "trace_limit": 50,
    }
    with httpx.Client(base_url="http://localhost:8000", timeout=90) as client:
        rebuilt_response = client.post("/api/v1/topology/rebuild", json=payload)
        rebuilt_response.raise_for_status()
        rebuilt = rebuilt_response.json()
        nodes = rebuilt.get("nodes", [])
        edges = rebuilt.get("edges", [])
        references = rebuilt.get("evidence_references", [])
        if not nodes or not edges:
            raise RuntimeError("the reconstructed graph contains no cross-service dependencies")
        if not references or not all(ref.startswith("telemetry://tempo/") for ref in references):
            raise RuntimeError("the graph is missing Tempo evidence references")
        print(
            f"PASS reconstructed {len(nodes)} services and {len(edges)} dependencies "
            f"from {rebuilt['trace_count']} traces"
        )

        latest_response = client.get("/api/v1/topology/latest")
        latest_response.raise_for_status()
        latest = latest_response.json()
        if latest.get("id") != rebuilt.get("id"):
            raise RuntimeError("the latest persisted snapshot does not match the rebuild")
        print(f"PASS persisted graph snapshot {rebuilt['id']}")

        first_edge = edges[0]
        caller = first_edge["caller"]
        callee = first_edge["callee"]
        dependencies_response = client.get(
            f"/api/v1/topology/latest/services/{caller}/dependencies",
            params={"transitive": "false"},
        )
        dependencies_response.raise_for_status()
        if callee not in dependencies_response.json().get("services", []):
            raise RuntimeError(f"direct dependency traversal lost {caller} -> {callee}")

        path_response = client.get(
            "/api/v1/topology/latest/path",
            params={"source": caller, "target": callee},
        )
        path_response.raise_for_status()
        if path_response.json().get("services") != [caller, callee]:
            raise RuntimeError("shortest-path traversal returned an unexpected path")
        print(f"PASS graph traversal {caller} -> {callee}")

        for edge in edges[:10]:
            print(
                f"  {edge['caller']} -> {edge['callee']} "
                f"requests={edge['request_count']} p95={edge['p95_latency_ms']:.2f}ms"
            )


def main() -> int:
    try:
        verify()
    except Exception as error:
        print(f"FAIL Milestone 3 topology verification: {error}", file=sys.stderr)
        return 1
    print("Milestone 3 service-graph verification passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

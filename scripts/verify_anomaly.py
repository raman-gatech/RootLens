#!/usr/bin/env python3
"""Run and verify a live evidence-linked anomaly analysis."""

import argparse
import sys
from datetime import UTC, datetime, timedelta
from uuid import UUID

import httpx


def verify(
    *,
    base_url: str,
    incident_end: datetime,
    incident_minutes: int,
    baseline_minutes: int,
) -> None:
    incident_start = incident_end - timedelta(minutes=incident_minutes)
    baseline_end = incident_start
    baseline_start = baseline_end - timedelta(minutes=baseline_minutes)
    payload = {
        "baseline_start": baseline_start.isoformat(),
        "baseline_end": baseline_end.isoformat(),
        "incident_start": incident_start.isoformat(),
        "incident_end": incident_end.isoformat(),
        "step_seconds": 30,
        "minimum_score": 0.5,
    }
    with httpx.Client(base_url=base_url, timeout=30) as client:
        response = client.post("/api/v1/anomalies/analyze", json=payload)
        response.raise_for_status()
        analysis = response.json()
        latest_response = client.get("/api/v1/anomalies/latest")
        latest_response.raise_for_status()
        latest = latest_response.json()

    UUID(analysis["id"])
    if latest["id"] != analysis["id"]:
        raise RuntimeError("latest anomaly snapshot does not match the persisted analysis")
    if analysis["evaluated_series"] < 1:
        raise RuntimeError("analysis evaluated no service/signal series")
    anomalies = analysis["anomalies"]
    if not anomalies:
        raise RuntimeError("analysis produced no ranked anomalies")
    if [item["rank"] for item in anomalies] != list(range(1, len(anomalies) + 1)):
        raise RuntimeError("anomaly ranks are not contiguous")
    scores = [item["score"] for item in anomalies]
    if scores != sorted(scores, reverse=True):
        raise RuntimeError("anomalies are not ordered by descending score")
    if not all(
        reference.startswith("telemetry://prometheus/")
        for reference in analysis["evidence_references"]
    ):
        raise RuntimeError("analysis contains a non-Prometheus evidence reference")
    top = anomalies[0]
    print(f"PASS ranked {len(anomalies)} anomalies across {analysis['evaluated_series']} series")
    print(
        f"PASS top anomaly rank=1 service={top['service']} signal={top['signal']} "
        f"score={top['score']:.3f}"
    )
    print(f"PASS persisted analysis {analysis['id']}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--incident-end", type=datetime.fromisoformat)
    parser.add_argument("--incident-minutes", type=int, default=5)
    parser.add_argument("--baseline-minutes", type=int, default=20)
    arguments = parser.parse_args()
    incident_end = arguments.incident_end or datetime.now(UTC)
    if incident_end.tzinfo is None:
        parser.error("--incident-end must be timezone-aware")
    if arguments.incident_minutes < 1 or arguments.baseline_minutes < 5:
        parser.error("incident must be >= 1 minute and baseline must be >= 5 minutes")
    try:
        verify(
            base_url=arguments.base_url,
            incident_end=incident_end,
            incident_minutes=arguments.incident_minutes,
            baseline_minutes=arguments.baseline_minutes,
        )
    except Exception as error:
        print(f"FAIL anomaly verification: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

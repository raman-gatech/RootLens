"""Regression tests for the live anomaly smoke verifier."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest

from scripts import verify_anomaly


class _Response:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self._payload


class _Client:
    def __init__(self, analysis: dict[str, Any]) -> None:
        self._analysis = analysis

    def __enter__(self) -> _Client:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def post(self, *_: object, **__: object) -> _Response:
        return _Response(self._analysis)

    def get(self, *_: object, **__: object) -> _Response:
        return _Response(self._analysis)


def _analysis() -> dict[str, Any]:
    return {
        "id": str(uuid4()),
        "evaluated_series": 12,
        "anomalies": [],
        "evidence_references": ["telemetry://prometheus/example"],
    }


def test_healthy_analysis_passes_without_forcing_an_anomaly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    analysis = _analysis()
    monkeypatch.setattr(
        verify_anomaly.httpx,
        "Client",
        lambda **_: _Client(analysis),
    )

    verify_anomaly.verify(
        base_url="http://rootlens.test",
        incident_end=datetime.now(UTC),
        incident_minutes=5,
        baseline_minutes=20,
        minimum_score=0.5,
        require_anomaly=False,
        timeout_seconds=30,
    )


def test_anomaly_can_be_required_for_fault_injection_runs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    analysis = _analysis()
    monkeypatch.setattr(
        verify_anomaly.httpx,
        "Client",
        lambda **_: _Client(analysis),
    )

    with pytest.raises(RuntimeError, match="produced no ranked anomalies"):
        verify_anomaly.verify(
            base_url="http://rootlens.test",
            incident_end=datetime.now(UTC),
            incident_minutes=5,
            baseline_minutes=20,
            minimum_score=0.5,
            require_anomaly=True,
            timeout_seconds=30,
        )

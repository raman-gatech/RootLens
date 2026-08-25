"""Tests for backend-neutral evidence contracts."""

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from rootlens.telemetry import QueryProvenance, QueryWindow, TelemetrySource


def test_query_window_requires_ordered_aware_timestamps() -> None:
    now = datetime.now(UTC)
    window = QueryWindow(start=now - timedelta(minutes=5), end=now)

    assert window.end > window.start

    with pytest.raises(ValidationError):
        QueryWindow(start=datetime(2026, 1, 1), end=datetime(2026, 1, 2))

    with pytest.raises(ValidationError):
        QueryWindow(start=now, end=now)


def test_provenance_has_a_source_scoped_reference() -> None:
    fetched = datetime(2026, 8, 24, tzinfo=UTC)
    provenance = QueryProvenance.create(
        source=TelemetrySource.PROMETHEUS,
        query="up",
        parameters={"time": "1"},
        retrieved_at=fetched,
    )

    assert provenance.query == "up"
    assert provenance.parameters == {"time": "1"}
    assert provenance.retrieved_at == fetched
    assert provenance.reference.startswith("telemetry://prometheus/")

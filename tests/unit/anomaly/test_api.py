"""Anomaly-analysis HTTP contract tests."""

from datetime import UTC, datetime, timedelta
from typing import cast

from httpx import ASGITransport, AsyncClient

from rootlens.anomaly import AnomalyAnalysisSnapshot, DetectorName
from rootlens.anomaly.service import AnomalyAnalysisService
from rootlens.api.anomalies import get_anomaly_service
from rootlens.config import Settings
from rootlens.main import create_app
from rootlens.telemetry import QueryWindow


class FakeAnomalyService:
    def __init__(self, snapshot: AnomalyAnalysisSnapshot) -> None:
        self.snapshot = snapshot
        self.calls = 0

    async def analyze(self, **_: object) -> AnomalyAnalysisSnapshot:
        self.calls += 1
        return self.snapshot

    async def latest(self) -> AnomalyAnalysisSnapshot:
        return self.snapshot


async def test_analysis_and_latest_snapshot_are_exposed() -> None:
    start = datetime(2026, 8, 25, 12, tzinfo=UTC)
    snapshot = AnomalyAnalysisSnapshot(
        baseline_window=QueryWindow(start=start, end=start + timedelta(minutes=10)),
        incident_window=QueryWindow(
            start=start + timedelta(minutes=10), end=start + timedelta(minutes=15)
        ),
        detectors=(DetectorName.STATISTICAL,),
        evaluated_series=1,
        minimum_score=0.5,
        anomalies=(),
        evidence_references=("telemetry://prometheus/test",),
    )
    app = create_app(Settings(telemetry_enabled=False))
    fake = FakeAnomalyService(snapshot)
    app.dependency_overrides[get_anomaly_service] = lambda: cast(AnomalyAnalysisService, fake)
    payload = {
        "baseline_start": start.isoformat(),
        "baseline_end": (start + timedelta(minutes=10)).isoformat(),
        "incident_start": (start + timedelta(minutes=10)).isoformat(),
        "incident_end": (start + timedelta(minutes=15)).isoformat(),
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        analyzed = await client.post("/api/v1/anomalies/analyze", json=payload)
        latest = await client.get("/api/v1/anomalies/latest")
        invalid = await client.post(
            "/api/v1/anomalies/analyze",
            json={**payload, "incident_start": (start + timedelta(minutes=5)).isoformat()},
        )
        oversized = await client.post(
            "/api/v1/anomalies/analyze",
            json={
                **payload,
                "baseline_start": (start - timedelta(days=3)).isoformat(),
                "step_seconds": 10,
            },
        )
    await app.state.database.close()
    await app.state.telemetry_gateway.aclose()

    assert analyzed.status_code == 201
    assert analyzed.json()["algorithm_version"] == "stat-iforest-v1"
    assert latest.status_code == 200
    assert invalid.status_code == 422
    assert oversized.status_code == 422
    assert fake.calls == 1

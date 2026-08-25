"""Incident HTTP and operator-console contract tests."""

from datetime import UTC, datetime, timedelta
from typing import cast

from httpx import ASGITransport, AsyncClient

from rootlens.api.incidents import get_investigation_service
from rootlens.config import Settings
from rootlens.investigation import AgentMode, Incident, Investigation, InvestigationStatus
from rootlens.investigation.contracts import Alert
from rootlens.investigation.service import InvestigationService
from rootlens.main import create_app
from rootlens.telemetry import QueryWindow


class FakeInvestigationService:
    def __init__(self) -> None:
        self.incident = _incident()
        self.run = Investigation(
            incident_id=self.incident.id,
            mode=AgentMode.MULTI,
            provider="deterministic-v1",
            status=InvestigationStatus.COMPLETED,
            started_at=self.incident.window.start,
            completed_at=self.incident.window.end,
        )
        self.alerts: list[Alert] = []

    async def create(self, incident: Incident) -> Incident:
        self.incident = incident
        return incident

    async def list(self, *, limit: int = 100) -> tuple[Incident, ...]:
        return (self.incident,)

    async def record_alert(self, alert: Alert) -> Alert:
        self.alerts.append(alert)
        return alert

    async def get(self, incident_id: object) -> Incident:
        return self.incident

    async def latest(self, incident_id: object) -> Investigation:
        return self.run

    async def investigate(self, incident_id: object, **_: object) -> Investigation:
        return self.run


async def test_incident_crud_investigation_views_and_dashboard_are_served() -> None:
    app = create_app(Settings(telemetry_enabled=False))
    fake = FakeInvestigationService()
    app.dependency_overrides[get_investigation_service] = lambda: cast(InvestigationService, fake)
    now = datetime(2026, 8, 25, 12, tzinfo=UTC)
    payload = {
        "title": "Checkout errors",
        "incident_start": (now - timedelta(minutes=5)).isoformat(),
        "incident_end": now.isoformat(),
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        dashboard = await client.get("/dashboard")
        script = await client.get("/dashboard/assets/app.js")
        created = await client.post("/api/v1/incidents", json=payload)
        listed = await client.get("/api/v1/incidents")
        investigated = await client.post(
            f"/api/v1/incidents/{fake.incident.id}/investigate",
            json={"mode": "multi_agent"},
        )
        evidence = await client.get(f"/api/v1/incidents/{fake.incident.id}/evidence")
        invalid = await client.post(
            "/api/v1/incidents",
            json={
                **payload,
                "incident_start": (now - timedelta(seconds=30)).isoformat(),
            },
        )
        webhook = await client.post(
            "/api/v1/alerts/prometheus",
            json={
                "status": "firing",
                "alerts": [
                    {
                        "status": "firing",
                        "labels": {"alertname": "HighLatency", "service": "checkout"},
                        "annotations": {"summary": "Checkout is slow"},
                        "startsAt": (now - timedelta(minutes=3)).isoformat(),
                    }
                ],
            },
        )
    await app.state.database.close()
    await app.state.telemetry_gateway.aclose()

    assert dashboard.status_code == 200
    assert "RootLens Operations" in dashboard.text
    assert script.status_code == 200
    assert created.status_code == 201
    assert listed.status_code == 200 and len(listed.json()) == 1
    assert investigated.status_code == 200
    assert investigated.json()["mode"] == "multi_agent"
    assert evidence.status_code == 200 and evidence.json() == []
    assert invalid.status_code == 422
    assert webhook.status_code == 201
    assert fake.alerts[0].source == "prometheus"


def _incident() -> Incident:
    now = datetime(2026, 8, 25, 12, tzinfo=UTC)
    return Incident(
        title="Checkout errors",
        window=QueryWindow(start=now - timedelta(minutes=5), end=now),
    )

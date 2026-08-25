from unittest.mock import AsyncMock, MagicMock

from httpx import ASGITransport, AsyncClient

from rootlens.api.health import get_engine
from rootlens.config import Settings
from rootlens.main import create_app


async def test_liveness_does_not_require_dependencies() -> None:
    app = create_app(
        Settings(
            database_url="postgresql+asyncpg://rootlens:rootlens@localhost:5432/rootlens",
            telemetry_enabled=False,
        )
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health/live")
    await app.state.database.close()
    await app.state.telemetry_gateway.aclose()

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "RootLens API"}


async def test_readiness_reports_database_failure_without_leaking_details() -> None:
    app = create_app(
        Settings(
            database_url="postgresql+asyncpg://rootlens:rootlens@localhost:5432/rootlens",
            telemetry_enabled=False,
        )
    )
    connection_context = MagicMock()
    connection_context.__aenter__ = AsyncMock(side_effect=RuntimeError("secret connection data"))
    connection_context.__aexit__ = AsyncMock(return_value=None)
    failing_engine = MagicMock()
    failing_engine.connect.return_value = connection_context
    app.dependency_overrides[get_engine] = lambda: failing_engine

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health/ready")
    await app.state.database.close()
    await app.state.telemetry_gateway.aclose()

    assert response.status_code == 503
    assert response.json() == {"status": "not_ready", "service": "RootLens API"}
    assert "secret" not in response.text

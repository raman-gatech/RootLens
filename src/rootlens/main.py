"""RootLens FastAPI application factory."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from opentelemetry import metrics
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from rootlens.api.health import router as health_router
from rootlens.api.topology import router as topology_router
from rootlens.config import Settings, get_settings
from rootlens.db.session import Database
from rootlens.observability import configure_telemetry
from rootlens.telemetry import TelemetryGateway
from rootlens.topology.repository import ServiceGraphRepository
from rootlens.topology.service import ServiceTopologyService


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or get_settings()
    configure_telemetry(resolved_settings)
    database = Database(resolved_settings.database_url)
    telemetry_gateway = TelemetryGateway.from_settings(resolved_settings)
    topology_service = ServiceTopologyService(
        gateway=telemetry_gateway,
        repository=ServiceGraphRepository(database),
        default_trace_limit=resolved_settings.topology_trace_limit,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        await asyncio.gather(database.close(), telemetry_gateway.aclose())

    app = FastAPI(
        title="RootLens API",
        version=resolved_settings.service_version,
        lifespan=lifespan,
    )
    app.state.database = database
    app.state.telemetry_gateway = telemetry_gateway
    app.state.topology_service = topology_service
    app.include_router(health_router)
    app.include_router(topology_router)

    meter = metrics.get_meter("rootlens.api")
    startup_counter = meter.create_counter(
        "rootlens.api.startups",
        description="Number of RootLens API process starts",
    )
    startup_counter.add(1)

    if resolved_settings.telemetry_enabled:
        FastAPIInstrumentor.instrument_app(app)
    return app


app = create_app()

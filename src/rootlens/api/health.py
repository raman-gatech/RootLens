"""Liveness and dependency-readiness endpoints."""

from typing import Annotated, cast

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

router = APIRouter(prefix="/health", tags=["health"])


class HealthResponse(BaseModel):
    status: str
    service: str


def get_engine(request: Request) -> AsyncEngine:
    return cast(AsyncEngine, request.app.state.database.engine)


@router.get("/live", response_model=HealthResponse)
async def liveness(request: Request) -> HealthResponse:
    return HealthResponse(status="ok", service=request.app.title)


@router.get("/ready", response_model=HealthResponse)
async def readiness(
    request: Request,
    response: Response,
    engine: Annotated[AsyncEngine, Depends(get_engine)],
) -> HealthResponse:
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
            revision = await connection.execute(text("SELECT version_num FROM alembic_version"))
            if revision.scalar_one_or_none() != request.app.state.settings.schema_revision:
                raise RuntimeError("database schema revision does not match application")
    except Exception:  # The response deliberately does not expose connection details.
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return HealthResponse(status="not_ready", service=request.app.title)
    return HealthResponse(status="ready", service=request.app.title)

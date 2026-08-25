"""HTTP endpoints for rebuilding and traversing trace-derived topology."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field, model_validator

from rootlens.telemetry import QueryWindow
from rootlens.topology import ServiceGraph, ServiceGraphSnapshot, ServicePath, ServiceSet
from rootlens.topology.errors import (
    ServiceNotFoundError,
    ServicePathNotFoundError,
    TopologyBuildError,
)
from rootlens.topology.service import ServiceTopologyService

router = APIRouter(prefix="/api/v1/topology", tags=["topology"])


class TopologyRebuildRequest(BaseModel):
    start: datetime
    end: datetime
    traceql: str = Field(default="{}", min_length=2, max_length=2_000)
    trace_limit: int | None = Field(default=None, ge=1, le=500)

    @model_validator(mode="after")
    def validate_window(self) -> TopologyRebuildRequest:
        QueryWindow(start=self.start, end=self.end)
        return self

    def window(self) -> QueryWindow:
        return QueryWindow(start=self.start, end=self.end)


def get_topology_service(request: Request) -> ServiceTopologyService:
    return cast(ServiceTopologyService, request.app.state.topology_service)


TopologyServiceDependency = Annotated[ServiceTopologyService, Depends(get_topology_service)]


@router.post(
    "/rebuild",
    response_model=ServiceGraphSnapshot,
    status_code=status.HTTP_201_CREATED,
)
async def rebuild_topology(
    payload: TopologyRebuildRequest,
    service: TopologyServiceDependency,
) -> ServiceGraphSnapshot:
    try:
        return await service.rebuild(
            payload.window(),
            traceql=payload.traceql,
            trace_limit=payload.trace_limit,
        )
    except TopologyBuildError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)
        ) from error


@router.get("/latest", response_model=ServiceGraphSnapshot)
async def latest_topology(service: TopologyServiceDependency) -> ServiceGraphSnapshot:
    snapshot = await service.latest()
    if snapshot is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="no topology snapshot exists"
        )
    return snapshot


@router.get("/latest/services/{service_name}/dependencies", response_model=ServiceSet)
async def service_dependencies(
    service_name: str,
    topology_service: TopologyServiceDependency,
    transitive: Annotated[bool, Query()] = True,
) -> ServiceSet:
    graph = ServiceGraph(await _latest(topology_service))
    try:
        if transitive:
            return graph.dependencies(service_name)
        return graph.direct_dependencies(service_name)
    except ServiceNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error


@router.get("/latest/services/{service_name}/callers", response_model=ServiceSet)
async def service_callers(
    service_name: str,
    topology_service: TopologyServiceDependency,
) -> ServiceSet:
    try:
        return ServiceGraph(await _latest(topology_service)).callers(service_name)
    except ServiceNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error


@router.get("/latest/path", response_model=ServicePath)
async def dependency_path(
    topology_service: TopologyServiceDependency,
    source: Annotated[str, Query(min_length=1)],
    target: Annotated[str, Query(min_length=1)],
) -> ServicePath:
    try:
        return ServiceGraph(await _latest(topology_service)).shortest_dependency_path(
            source, target
        )
    except (ServiceNotFoundError, ServicePathNotFoundError) as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error


async def _latest(service: ServiceTopologyService) -> ServiceGraphSnapshot:
    snapshot = await service.latest()
    if snapshot is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="no topology snapshot exists"
        )
    return snapshot

"""Human-gated remediation API."""

from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from rootlens.investigation.errors import IncidentNotFoundError
from rootlens.remediation import ActionType, RemediationPlan
from rootlens.remediation.service import RemediationError, RemediationService
from rootlens.security import get_principal

router = APIRouter(prefix="/api/v1/incidents/{incident_id}", tags=["remediation"])


class ProposeRemediationRequest(BaseModel):
    action_type: ActionType
    namespace: str = Field(min_length=1, max_length=63)
    target: str = Field(min_length=1, max_length=253)
    target_service: str = Field(min_length=1, max_length=160)
    rationale: str = Field(min_length=1, max_length=2_000)


class RemediationDecisionRequest(BaseModel):
    plan_id: UUID
    actor: str = Field(min_length=2, max_length=160)
    reason: str = Field(min_length=2, max_length=1_000)


def get_remediation_service(request: Request) -> RemediationService:
    return cast(RemediationService, request.app.state.remediation_service)


RemediationServiceDependency = Annotated[RemediationService, Depends(get_remediation_service)]


@router.get("/remediation", response_model=RemediationPlan)
async def get_remediation(
    incident_id: UUID, service: RemediationServiceDependency
) -> RemediationPlan:
    try:
        plan = await service.latest(incident_id)
    except IncidentNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    if plan is None:
        raise HTTPException(status_code=404, detail="incident has no remediation plan")
    return plan


@router.post("/remediation", response_model=RemediationPlan, status_code=status.HTTP_201_CREATED)
async def propose_remediation(
    incident_id: UUID,
    payload: ProposeRemediationRequest,
    service: RemediationServiceDependency,
) -> RemediationPlan:
    try:
        return await service.propose(incident_id, **payload.model_dump())
    except (IncidentNotFoundError, RemediationError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.post("/approve-remediation", response_model=RemediationPlan)
async def approve_remediation(
    incident_id: UUID,
    payload: RemediationDecisionRequest,
    request: Request,
    service: RemediationServiceDependency,
) -> RemediationPlan:
    actor = _verified_actor(request, payload.actor)
    try:
        return await service.approve_and_execute(
            incident_id,
            payload.plan_id,
            actor=actor,
            reason=payload.reason,
        )
    except RemediationError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.post("/reject-remediation", response_model=RemediationPlan)
async def reject_remediation(
    incident_id: UUID,
    payload: RemediationDecisionRequest,
    request: Request,
    service: RemediationServiceDependency,
) -> RemediationPlan:
    actor = _verified_actor(request, payload.actor)
    try:
        return await service.reject(
            incident_id,
            payload.plan_id,
            actor=actor,
            reason=payload.reason,
        )
    except RemediationError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


def _verified_actor(request: Request, requested_actor: str) -> str:
    principal = get_principal(request.state)
    if principal.authenticated and requested_actor != principal.name:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="approval actor must match the authenticated principal",
        )
    return principal.name if principal.authenticated else requested_actor

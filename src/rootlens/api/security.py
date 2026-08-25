"""Authenticated-principal inspection endpoint."""

from fastapi import APIRouter, Request
from pydantic import BaseModel

from rootlens.security import get_principal

router = APIRouter(prefix="/api/v1/auth", tags=["security"])


class PrincipalResponse(BaseModel):
    principal: str
    permissions: tuple[str, ...]
    authenticated: bool


@router.get("/me", response_model=PrincipalResponse)
async def who_am_i(request: Request) -> PrincipalResponse:
    principal = get_principal(request.state)
    return PrincipalResponse(
        principal=principal.name,
        permissions=tuple(sorted(permission.value for permission in principal.permissions)),
        authenticated=principal.authenticated,
    )

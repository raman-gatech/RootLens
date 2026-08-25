"""Serve the dependency-free RootLens operator console."""

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse, RedirectResponse

router = APIRouter(include_in_schema=False)
_UI_DIR = Path(__file__).resolve().parent.parent / "ui"


@router.get("/")
async def root() -> RedirectResponse:
    return RedirectResponse(url="/dashboard", status_code=307)


@router.get("/dashboard")
async def dashboard() -> FileResponse:
    return FileResponse(_UI_DIR / "index.html")

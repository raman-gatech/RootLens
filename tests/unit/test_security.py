"""Authentication and function-level authorization tests."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from starlette.requests import Request

from rootlens.api.remediation import _verified_actor
from rootlens.config import Settings
from rootlens.main import create_app
from rootlens.security import Permission, Principal

READ_TOKEN = "read-only-token-that-is-at-least-32-characters"
OPERATOR_TOKEN = "operator-token-that-is-at-least-32-characters"


def _credentials(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "credentials": [
                    {
                        "principal": "viewer@example.com",
                        "token_sha256": hashlib.sha256(READ_TOKEN.encode()).hexdigest(),
                        "permissions": ["read"],
                    },
                    {
                        "principal": "oncall@example.com",
                        "token_sha256": hashlib.sha256(OPERATOR_TOKEN.encode()).hexdigest(),
                        "permissions": [
                            "read",
                            "investigate",
                            "ingest",
                            "publish",
                            "remediate",
                        ],
                    },
                ]
            }
        ),
        encoding="utf-8",
    )


async def test_api_authentication_and_function_permissions(tmp_path: Path) -> None:
    credential_file = tmp_path / "credentials.json"
    _credentials(credential_file)
    app = create_app(
        Settings(
            environment="production",
            database_url="postgresql+asyncpg://rootlens_app:production-secret@localhost/rootlens",
            telemetry_enabled=False,
            auth_enabled=True,
            auth_credentials_file=str(credential_file),
            trusted_hosts=("test",),
            docs_enabled=False,
        )
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        unauthenticated = await client.get("/api/v1/auth/me")
        viewer = await client.get(
            "/api/v1/auth/me", headers={"Authorization": f"Bearer {READ_TOKEN}"}
        )
        forbidden = await client.post(
            "/api/v1/incidents",
            headers={"Authorization": f"Bearer {READ_TOKEN}"},
            json={},
        )
        authorized = await client.post(
            "/api/v1/incidents",
            headers={"Authorization": f"Bearer {OPERATOR_TOKEN}"},
            json={},
        )
    await app.state.database.close()
    await app.state.telemetry_gateway.aclose()

    assert unauthenticated.status_code == 401
    assert unauthenticated.headers["www-authenticate"] == "Bearer"
    assert unauthenticated.headers["strict-transport-security"].startswith("max-age=")
    assert viewer.status_code == 200
    assert viewer.json() == {
        "principal": "viewer@example.com",
        "permissions": ["read"],
        "authenticated": True,
    }
    assert viewer.headers["x-content-type-options"] == "nosniff"
    assert viewer.headers["x-request-id"]
    assert viewer.headers["cache-control"] == "no-store"
    assert forbidden.status_code == 403
    assert authorized.status_code == 422


def test_remediation_actor_is_bound_to_authenticated_principal() -> None:
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/",
            "headers": [],
            "state": {
                "principal": Principal(
                    "oncall@example.com",
                    frozenset({Permission.REMEDIATE}),
                    authenticated=True,
                )
            },
        }
    )

    assert _verified_actor(request, "oncall@example.com") == "oncall@example.com"
    with pytest.raises(HTTPException) as error:
        _verified_actor(request, "someone-else@example.com")
    assert error.value.status_code == 403

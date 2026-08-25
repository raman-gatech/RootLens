"""Authentication, authorization, and HTTP response hardening."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class Permission(StrEnum):
    READ = "read"
    INVESTIGATE = "investigate"
    INGEST = "ingest"
    PUBLISH = "publish"
    REMEDIATE = "remediate"


ALL_PERMISSIONS = frozenset(Permission)


@dataclass(frozen=True)
class Principal:
    name: str
    permissions: frozenset[Permission]
    authenticated: bool


class Credential(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    principal: str = Field(min_length=2, max_length=160, pattern=r"^[\w.@:+-]+$")
    token_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    permissions: frozenset[Permission] = Field(min_length=1)


class CredentialFile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    credentials: tuple[Credential, ...] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def reject_duplicates(self) -> CredentialFile:
        principals = [item.principal for item in self.credentials]
        digests = [item.token_sha256 for item in self.credentials]
        if len(principals) != len(set(principals)):
            raise ValueError("credential principals must be unique")
        if len(digests) != len(set(digests)):
            raise ValueError("credential token digests must be unique")
        return self


class CredentialStore:
    """Authenticate opaque bearer tokens against non-reversible SHA-256 digests."""

    def __init__(self, credentials: tuple[Credential, ...]) -> None:
        self._credentials = credentials

    @classmethod
    def from_file(cls, filename: str) -> CredentialStore:
        path = Path(filename)
        if not path.is_file():
            raise RuntimeError("authentication credential file does not exist")
        if path.stat().st_size > 65_536:
            raise RuntimeError("authentication credential file exceeds 64 KiB")
        if path.stat().st_mode & 0o022:
            raise RuntimeError("authentication credential file must not be group/world writable")
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
            parsed = CredentialFile.model_validate(document)
        except (OSError, json.JSONDecodeError, ValidationError) as error:
            raise RuntimeError("authentication credential file is invalid") from error
        return cls(parsed.credentials)

    def authenticate(self, token: str) -> Principal | None:
        if not 32 <= len(token) <= 4_096:
            return None
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        matched: Credential | None = None
        for credential in self._credentials:
            if hmac.compare_digest(digest, credential.token_sha256):
                matched = credential
        if matched is None:
            return None
        return Principal(matched.principal, matched.permissions, authenticated=True)


class ApiSecurityMiddleware:
    """Enforce bearer authentication and function-level API permissions."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        enabled: bool,
        store: CredentialStore | None,
        hsts_enabled: bool,
    ) -> None:
        self._app = app
        self._enabled = enabled
        self._store = store
        self._hsts_enabled = hsts_enabled

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        state = scope.setdefault("state", {})
        state["request_id"] = uuid4().hex
        path = str(scope.get("path", ""))
        if not path.startswith("/api/v1"):
            state["principal"] = Principal("anonymous", frozenset(), authenticated=False)
            await self._with_security_headers(scope, receive, send)
            return

        if not self._enabled:
            state["principal"] = Principal("development", ALL_PERMISSIONS, authenticated=False)
            await self._with_security_headers(scope, receive, send)
            return

        token = _bearer_token(scope)
        principal = self._store.authenticate(token) if self._store and token else None
        if principal is None:
            await _auth_error(
                scope,
                receive,
                send,
                401,
                "authentication required",
                state["request_id"],
                self._hsts_enabled,
            )
            return
        required = _required_permission(str(scope.get("method", "GET")), path)
        if required not in principal.permissions:
            await _auth_error(
                scope,
                receive,
                send,
                403,
                "permission denied",
                state["request_id"],
                self._hsts_enabled,
            )
            return
        state["principal"] = principal
        await self._with_security_headers(scope, receive, send)

    async def _with_security_headers(self, scope: Scope, receive: Receive, send: Send) -> None:
        request_id = str(scope["state"]["request_id"])

        async def secure_send(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.extend(
                    [
                        (b"x-content-type-options", b"nosniff"),
                        (b"x-frame-options", b"DENY"),
                        (b"referrer-policy", b"no-referrer"),
                        (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
                        (
                            b"content-security-policy",
                            b"default-src 'self'; object-src 'none'; frame-ancestors 'none'; "
                            b"base-uri 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'",
                        ),
                        (b"x-request-id", request_id.encode("ascii")),
                    ]
                )
                if str(scope.get("path", "")).startswith("/api/v1"):
                    headers.append((b"cache-control", b"no-store"))
                if self._hsts_enabled:
                    headers.append(
                        (b"strict-transport-security", b"max-age=31536000; includeSubDomains")
                    )
                message["headers"] = headers
            await send(message)

        await self._app(scope, receive, secure_send)


def get_principal(state: Any) -> Principal:
    principal = getattr(state, "principal", None)
    if not isinstance(principal, Principal):
        return Principal("anonymous", frozenset(), authenticated=False)
    return principal


def _required_permission(method: str, path: str) -> Permission:
    if method in {"GET", "HEAD"}:
        return Permission.READ
    if path == "/api/v1/alerts/prometheus":
        return Permission.INGEST
    if path == "/api/v1/evaluations":
        return Permission.PUBLISH
    if re.search(r"/(?:approve-|reject-)?remediation$", path):
        return Permission.REMEDIATE
    return Permission.INVESTIGATE


def _bearer_token(scope: Scope) -> str | None:
    for name, value in scope.get("headers", []):
        if bytes(name).lower() != b"authorization":
            continue
        try:
            scheme, token = bytes(value).decode("ascii").split(" ", 1)
        except (UnicodeDecodeError, ValueError):
            return None
        if scheme.lower() != "bearer" or not token:
            return None
        return token
    return None


async def _auth_error(
    scope: Scope,
    receive: Receive,
    send: Send,
    status: int,
    detail: str,
    request_id: str,
    hsts_enabled: bool,
) -> None:
    headers = {
        "WWW-Authenticate": "Bearer",
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "X-Request-ID": request_id,
    }
    if hsts_enabled:
        headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response = JSONResponse(
        {"detail": detail, "request_id": request_id},
        status_code=status,
        headers=headers,
    )
    await response(scope, receive, send)

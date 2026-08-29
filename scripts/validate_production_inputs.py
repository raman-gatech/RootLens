"""Validate protected production inputs without printing secret material."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import stat
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import yaml

_ALLOWED_PERMISSIONS = {"read", "investigate", "ingest", "publish", "remediate"}
_TOKEN_DIGEST = re.compile(r"^[a-f0-9]{64}$")


class ProductionInputError(ValueError):
    """Raised when a protected deployment input is incomplete or unsafe."""


def validate_production_inputs(
    *,
    kubeconfig_path: Path,
    kube_context: str,
    credentials_path: Path,
    smoke_token_path: Path,
    database_url_path: Path,
    openai_api_key_path: Path,
) -> None:
    """Validate all non-TLS protected inputs used by production promotion."""
    for path in (
        kubeconfig_path,
        credentials_path,
        smoke_token_path,
        database_url_path,
        openai_api_key_path,
    ):
        _require_private_file(path)
    _validate_kubeconfig(kubeconfig_path, kube_context)
    _validate_credentials(credentials_path, smoke_token_path)
    _validate_database_url(database_url_path)
    _validate_openai_key(openai_api_key_path)


def _require_private_file(path: Path) -> None:
    if not path.is_file() or path.stat().st_size == 0:
        raise ProductionInputError(f"{path.name} must be a non-empty regular file")
    if stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise ProductionInputError(f"{path.name} must not be accessible by group or others")


def _validate_kubeconfig(path: Path, expected_context: str) -> None:
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as error:
        raise ProductionInputError("kubeconfig must contain valid YAML") from error
    if not isinstance(document, dict):
        raise ProductionInputError("kubeconfig must contain a Kubernetes configuration object")
    contexts = {
        item.get("name")
        for item in document.get("contexts", [])
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    }
    if not expected_context or expected_context not in contexts:
        raise ProductionInputError("configured production context is absent from kubeconfig")
    if not document.get("clusters") or not document.get("users"):
        raise ProductionInputError("kubeconfig must include cluster and user credentials")


def _validate_credentials(credentials_path: Path, smoke_token_path: Path) -> None:
    try:
        document: Any = json.loads(credentials_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ProductionInputError("authentication credentials must contain valid JSON") from error
    entries = document.get("credentials") if isinstance(document, dict) else None
    if not isinstance(entries, list) or not entries:
        raise ProductionInputError("at least one authentication credential is required")
    seen_principals: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise ProductionInputError("each authentication credential must be an object")
        principal = entry.get("principal")
        digest = entry.get("token_sha256")
        permissions = entry.get("permissions")
        if not isinstance(principal, str) or not principal.strip():
            raise ProductionInputError("each authentication credential needs a principal")
        if principal in seen_principals:
            raise ProductionInputError("authentication principals must be unique")
        seen_principals.add(principal)
        if not isinstance(digest, str) or not _TOKEN_DIGEST.fullmatch(digest):
            raise ProductionInputError(
                "each token digest must be 64 lowercase hexadecimal characters"
            )
        if (
            not isinstance(permissions, list)
            or not permissions
            or len(permissions) != len(set(permissions))
            or not set(permissions) <= _ALLOWED_PERMISSIONS
        ):
            raise ProductionInputError("credential permissions must be unique allowed values")

    smoke_token = smoke_token_path.read_text(encoding="utf-8").strip()
    if len(smoke_token.encode()) < 32:
        raise ProductionInputError("smoke token must contain at least 32 bytes")
    smoke_digest = hashlib.sha256(smoke_token.encode()).hexdigest()
    if not any(
        entry["token_sha256"] == smoke_digest and "read" in entry["permissions"]
        for entry in entries
    ):
        raise ProductionInputError("smoke token must match a credential with read permission")


def _validate_database_url(path: Path) -> None:
    database_url = path.read_text(encoding="utf-8").strip()
    parsed = urlsplit(database_url)
    if parsed.scheme != "postgresql+asyncpg":
        raise ProductionInputError("database URL must use postgresql+asyncpg")
    if parsed.hostname in {None, "localhost", "127.0.0.1", "::1"}:
        raise ProductionInputError("database URL must use a non-loopback hostname")
    if not parsed.username or not parsed.password or parsed.path in {"", "/"}:
        raise ProductionInputError("database URL must include username, password, and database")
    if parse_qs(parsed.query).get("ssl") != ["verify-full"]:
        raise ProductionInputError("database URL must require ssl=verify-full")


def _validate_openai_key(path: Path) -> None:
    key = path.read_text(encoding="utf-8").strip()
    if len(key) < 20 or any(character.isspace() for character in key):
        raise ProductionInputError("OpenAI API key is malformed")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kubeconfig", type=Path, required=True)
    parser.add_argument("--kube-context", required=True)
    parser.add_argument("--credentials", type=Path, required=True)
    parser.add_argument("--smoke-token", type=Path, required=True)
    parser.add_argument("--database-url", type=Path, required=True)
    parser.add_argument("--openai-api-key", type=Path, required=True)
    arguments = parser.parse_args()
    validate_production_inputs(
        kubeconfig_path=arguments.kubeconfig,
        kube_context=arguments.kube_context,
        credentials_path=arguments.credentials,
        smoke_token_path=arguments.smoke_token,
        database_url_path=arguments.database_url,
        openai_api_key_path=arguments.openai_api_key,
    )
    print("Protected production inputs passed validation.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

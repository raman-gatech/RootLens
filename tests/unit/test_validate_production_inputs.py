"""Protected production input validation tests."""

import hashlib
import json
from pathlib import Path

import pytest

from scripts.validate_production_inputs import ProductionInputError, validate_production_inputs


def _private_file(path: Path, value: str) -> Path:
    path.write_text(value, encoding="utf-8")
    path.chmod(0o600)
    return path


def _inputs(tmp_path: Path) -> dict[str, object]:
    smoke_token = "a-production-smoke-token-with-more-than-32-bytes"
    digest = hashlib.sha256(smoke_token.encode()).hexdigest()
    kubeconfig = {
        "apiVersion": "v1",
        "kind": "Config",
        "clusters": [{"name": "prod", "cluster": {"server": "https://k8s.example.net"}}],
        "contexts": [{"name": "rootlens-prod", "context": {"cluster": "prod", "user": "deployer"}}],
        "users": [{"name": "deployer", "user": {"token": "redacted"}}],
    }
    credentials = {
        "credentials": [
            {
                "principal": "smoke-test",
                "token_sha256": digest,
                "permissions": ["read"],
            }
        ]
    }
    return {
        "kubeconfig_path": _private_file(tmp_path / "kubeconfig.yaml", json.dumps(kubeconfig)),
        "kube_context": "rootlens-prod",
        "credentials_path": _private_file(tmp_path / "credentials.json", json.dumps(credentials)),
        "smoke_token_path": _private_file(tmp_path / "smoke-token", smoke_token),
        "database_url_path": _private_file(
            tmp_path / "database-url",
            "postgresql+asyncpg://rootlens:secret@db.example.net/rootlens?ssl=verify-full",
        ),
        "openai_api_key_path": _private_file(
            tmp_path / "openai-api-key", "sk-test-key-that-is-long-enough"
        ),
    }


def test_accepts_complete_private_production_inputs(tmp_path: Path) -> None:
    validate_production_inputs(**_inputs(tmp_path))


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("kube_context", "missing-context", "absent from kubeconfig"),
        ("smoke_token_path", "short", "at least 32 bytes"),
        (
            "database_url_path",
            "postgresql+asyncpg://rootlens:secret@localhost/rootlens?ssl=verify-full",
            "non-loopback",
        ),
        ("openai_api_key_path", "contains whitespace", "malformed"),
    ],
)
def test_rejects_unsafe_production_inputs(
    tmp_path: Path, field: str, value: str, message: str
) -> None:
    arguments = _inputs(tmp_path)
    if field.endswith("_path"):
        arguments[field] = _private_file(Path(arguments[field]), value)
    else:
        arguments[field] = value
    with pytest.raises(ProductionInputError, match=message):
        validate_production_inputs(**arguments)


def test_rejects_group_readable_secret(tmp_path: Path) -> None:
    arguments = _inputs(tmp_path)
    credentials_path = Path(arguments["credentials_path"])
    credentials_path.chmod(0o640)
    with pytest.raises(ProductionInputError, match="group or others"):
        validate_production_inputs(**arguments)

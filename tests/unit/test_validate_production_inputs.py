"""Unit tests for production input validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.validate_production_inputs import (
    ValidationError,
    validate_auth_credentials,
    validate_database_url,
    validate_hostname,
    validate_image_digest,
    validate_oci_budget,
)


def test_validate_hostname_valid() -> None:
    validate_hostname("rootlens.prod.mycompany.org")


def test_validate_hostname_invalid() -> None:
    with pytest.raises(ValidationError):
        validate_hostname("rootlens.example.com")
    with pytest.raises(ValidationError):
        validate_hostname("invalid_hostname")


def test_validate_image_digest() -> None:
    valid = "ghcr.io/raman-gatech/rootlens@sha256:" + "a" * 64
    validate_image_digest(valid)

    with pytest.raises(ValidationError):
        validate_image_digest("ghcr.io/raman-gatech/rootlens:latest")


def test_validate_database_url() -> None:
    validate_database_url("postgresql+asyncpg://admin:supersecret@db.internal:5432/rootlens")

    with pytest.raises(ValidationError, match="scheme"):
        validate_database_url("sqlite:///foo.db")

    with pytest.raises(ValidationError, match="default dev"):
        validate_database_url("postgresql+asyncpg://rootlens:rootlens@localhost:5432/rootlens")


def test_validate_auth_credentials(tmp_path: Path) -> None:
    auth_file = tmp_path / "creds.json"
    auth_file.write_text('{"users": []}')
    validate_auth_credentials(auth_file)

    with pytest.raises(ValidationError):
        validate_auth_credentials(tmp_path / "missing.json")


def test_validate_oci_budget() -> None:
    validate_oci_budget(node_count=2, node_ocpus=1, node_memory_in_gbs=6)
    validate_oci_budget(node_count=4, node_ocpus=1, node_memory_in_gbs=6)

    with pytest.raises(ValidationError, match="OCPUs"):
        validate_oci_budget(node_count=5, node_ocpus=1, node_memory_in_gbs=6)

    with pytest.raises(ValidationError, match="memory"):
        validate_oci_budget(node_count=2, node_ocpus=2, node_memory_in_gbs=16)

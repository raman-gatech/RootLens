"""Unit tests for PostgreSQL SSL and custom CA certificate handling."""

from __future__ import annotations

import ssl
from pathlib import Path

import pytest

from rootlens.db.ssl import build_ssl_context


def test_build_ssl_context_disabled() -> None:
    assert build_ssl_context(ssl_mode="disable") is False
    assert build_ssl_context(ssl_mode="false") is False


def test_build_ssl_context_require_no_ca() -> None:
    context = build_ssl_context(ssl_mode="require")
    assert isinstance(context, ssl.SSLContext)
    assert context.check_hostname is True


def test_build_ssl_context_verify_ca_no_ca() -> None:
    context = build_ssl_context(ssl_mode="verify-ca")
    assert isinstance(context, ssl.SSLContext)
    assert context.check_hostname is False


def test_build_ssl_context_missing_ca_file(tmp_path: Path) -> None:
    missing = tmp_path / "nonexistent-ca.crt"
    with pytest.raises(FileNotFoundError, match="Database CA certificate file not found"):
        build_ssl_context(ca_cert_file=missing)


def test_build_ssl_context_default_none() -> None:
    assert build_ssl_context(ssl_mode="prefer") is None

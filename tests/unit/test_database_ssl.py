"""PostgreSQL private-CA TLS configuration tests."""

import ssl
from unittest.mock import Mock, patch

import pytest
from sqlalchemy.engine import URL

from rootlens.db.ssl import database_engine_configuration


def test_private_ca_builds_hostname_verifying_asyncpg_context() -> None:
    context = Mock(spec=ssl.SSLContext)
    with patch("rootlens.db.ssl.ssl.create_default_context", return_value=context) as create:
        url, connect_args = database_engine_configuration(
            "postgresql+asyncpg://rootlens:secret@db.internal/rootlens?"
            "ssl=verify-full&sslrootcert=/run/secrets/rootlens-database/ca.crt"
        )

    assert isinstance(url, URL)
    assert dict(url.query) == {}
    assert connect_args == {"ssl": context}
    create.assert_called_once_with(cafile="/run/secrets/rootlens-database/ca.crt")
    assert context.check_hostname is True
    assert context.verify_mode == ssl.CERT_REQUIRED


def test_system_ca_database_url_is_passed_through() -> None:
    raw = "postgresql+asyncpg://rootlens:secret@db.example.net/rootlens?ssl=verify-full"

    assert database_engine_configuration(raw) == (raw, {})


def test_private_ca_requires_verify_full() -> None:
    with pytest.raises(ValueError, match="requires ssl=verify-full"):
        database_engine_configuration(
            "postgresql+asyncpg://rootlens:secret@db.internal/rootlens?"
            "ssl=require&sslrootcert=/run/secrets/rootlens-database/ca.crt"
        )

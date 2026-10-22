"""PostgreSQL TLS configuration shared by runtime and migrations."""

from __future__ import annotations

import ssl
from typing import Any

from sqlalchemy.engine import URL, make_url


def database_engine_configuration(database_url: str) -> tuple[str | URL, dict[str, Any]]:
    """Build an asyncpg SSL context when a private database CA is supplied."""
    url = make_url(database_url)
    root_certificate = url.query.get("sslrootcert")
    if root_certificate is None:
        return database_url, {}
    if not isinstance(root_certificate, str):
        raise ValueError("sslrootcert must be specified exactly once")
    if url.query.get("ssl") != "verify-full":
        raise ValueError("sslrootcert requires ssl=verify-full")
    context = ssl.create_default_context(cafile=root_certificate)
    context.check_hostname = True
    context.verify_mode = ssl.CERT_REQUIRED
    sanitized_url = url.difference_update_query(["ssl", "sslrootcert"])
    return sanitized_url, {"ssl": context}

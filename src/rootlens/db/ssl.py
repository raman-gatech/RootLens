"""Database SSL configuration for PostgreSQL connections."""

from __future__ import annotations

import os
import ssl as _stdlib_ssl
from pathlib import Path


def build_ssl_context(
    ca_cert_file: str | Path | None = None,
    *,
    ssl_mode: str | None = None,
) -> _stdlib_ssl.SSLContext | bool | None:
    """Build an SSLContext for asyncpg or SQLAlchemy async engine.

    Returns:
        - ssl.SSLContext configured with CA certificate if provided.
        - True if ssl_mode is 'require' or 'verify-full' without a custom CA file.
        - None or False if SSL is disabled.
    """
    ca_path = ca_cert_file or os.getenv("ROOTLENS_DATABASE_CA_CERT_FILE")
    mode = ssl_mode or os.getenv("ROOTLENS_DATABASE_SSL_MODE", "prefer").lower()

    if mode in {"disable", "allow", "false", "0"}:
        return False

    if ca_path:
        path = Path(ca_path)
        if not path.is_file():
            raise FileNotFoundError(f"Database CA certificate file not found: {path}")
        context = _stdlib_ssl.create_default_context(cafile=str(path))
        if mode == "verify-ca":
            context.check_hostname = False
        else:
            context.check_hostname = True
        return context

    if mode in {"require", "verify-ca", "verify-full", "true", "1"}:
        context = _stdlib_ssl.create_default_context()
        if mode == "verify-ca":
            context.check_hostname = False
        return context

    return None

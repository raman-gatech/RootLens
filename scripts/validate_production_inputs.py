"""Validate pre-flight production configuration and secret requirements."""

from __future__ import annotations

import argparse
import os
import re
import socket
from pathlib import Path

_IMAGE_PATTERN = re.compile(r"^ghcr\.io/raman-gatech/rootlens@sha256:[a-f0-9]{64}$")
_DNS_NAME = re.compile(
    r"(?=^.{4,253}$)(?!-)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
    r"[a-z](?:[a-z0-9-]{0,61}[a-z0-9])?$"
)


class ValidationError(Exception):
    """Raised when production validation fails."""


def validate_hostname(hostname: str) -> None:
    if not _DNS_NAME.fullmatch(hostname) or hostname.endswith(".example.com"):
        raise ValidationError(f"Invalid production hostname: {hostname!r}")


def check_dns_resolution(hostname: str) -> str:
    validate_hostname(hostname)
    try:
        ip = socket.gethostbyname(hostname)
        return ip
    except socket.gaierror as err:
        raise ValidationError(f"Failed to resolve DNS for {hostname}: {err}") from err


def validate_image_digest(image: str) -> None:
    if not _IMAGE_PATTERN.fullmatch(image):
        raise ValidationError(f"Image must be pinned to immutable sha256 digest: {image!r}")


def validate_database_url(url: str) -> None:
    if not url.startswith("postgresql+asyncpg://"):
        raise ValidationError("Database URL must use postgresql+asyncpg:// scheme")
    if "rootlens:rootlens@" in url:
        raise ValidationError("Production cannot use default dev database credentials")


def validate_auth_credentials(file_path: str | Path) -> None:
    path = Path(file_path)
    if not path.is_file():
        raise ValidationError(f"Auth credentials file does not exist: {path}")


def validate_oci_budget(node_count: int, node_ocpus: int, node_memory_in_gbs: int) -> None:
    total_ocpus = node_count * node_ocpus
    total_memory = node_count * node_memory_in_gbs
    if total_ocpus > 4:
        raise ValidationError(
            f"Total OCPUs ({total_ocpus}) exceeds OCI Always Free limit of 4 OCPUs"
        )
    if total_memory > 24:
        raise ValidationError(
            f"Total memory ({total_memory} GB) exceeds OCI Always Free limit of 24 GB"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hostname", help="Public production hostname")
    parser.add_argument("--image", help="Production container image with sha256 digest")
    parser.add_argument("--database-url", help="Production PostgreSQL connection string")
    parser.add_argument("--auth-file", help="Path to auth credentials JSON file")
    parser.add_argument("--node-count", type=int, default=2)
    parser.add_argument("--node-ocpus", type=int, default=1)
    parser.add_argument("--node-memory", type=int, default=6)
    parser.add_argument("--check-dns", action="store_true", help="Attempt live DNS lookup")
    args = parser.parse_args()

    try:
        if args.hostname:
            validate_hostname(args.hostname)
            if args.check_dns:
                ip = check_dns_resolution(args.hostname)
                print(f"DNS resolved {args.hostname} -> {ip}")
        if args.image:
            validate_image_digest(args.image)
        if args.database_url:
            validate_database_url(args.database_url)
        if args.auth_file:
            validate_auth_credentials(args.auth_file)
        validate_oci_budget(args.node_count, args.node_ocpus, args.node_memory)
        print("All production input validations passed successfully.")
        return 0
    except ValidationError as err:
        print(f"Validation Error: {err}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Export the local kind reader token/CA into an ignored Compose-only directory."""

from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
from pathlib import Path


def main() -> int:
    project = Path(__file__).resolve().parent.parent
    destination = project / ".runtime" / "kubernetes"
    destination.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(destination, 0o700)
    command = [
        "kubectl",
        "--context",
        "kind-rootlens",
        "--namespace",
        "rootlens",
        "get",
        "secret",
        "rootlens-reader-token",
        "--output",
        "json",
    ]
    try:
        payload = json.loads(subprocess.check_output(command, text=True))
        data = payload["data"]
        token = base64.b64decode(data["token"], validate=True)
        certificate = base64.b64decode(data["ca.crt"], validate=True)
    except (subprocess.CalledProcessError, KeyError, ValueError, json.JSONDecodeError) as error:
        print(f"failed to export Kubernetes reader credentials: {error}", file=sys.stderr)
        return 1
    _write_secret(destination / "token", token)
    _write_secret(destination / "ca.crt", certificate)
    print("Exported least-privilege Kubernetes reader credentials for local Compose.")
    return 0


def _write_secret(path: Path, value: bytes) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(value)
    os.chmod(temporary, 0o600)
    temporary.replace(path)
    os.chmod(path, 0o600)


if __name__ == "__main__":
    raise SystemExit(main())

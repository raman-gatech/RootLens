"""Narrow kubectl adapter used only by the external benchmark controller."""

import asyncio
from pathlib import Path

from experiment_controller.contracts import ExperimentSpec


class KubectlError(RuntimeError):
    pass


class KubectlRunner:
    def __init__(
        self,
        *,
        binary: Path = Path("kubectl"),
        context: str = "kind-rootlens",
    ) -> None:
        self._binary = str(binary)
        self._context = context

    async def require_target(self, spec: ExperimentSpec) -> None:
        output = await self._run(
            "get",
            "pods",
            "--namespace",
            spec.namespace,
            "--selector",
            f"app.kubernetes.io/component={spec.target_service}",
            "--output",
            "name",
        )
        if not output.strip():
            raise KubectlError(f"no eligible pods found for service {spec.target_service!r}")

    async def server_dry_run(self, manifest: str) -> None:
        await self._run("apply", "--dry-run=server", "--filename", "-", stdin=manifest)

    async def apply(self, manifest: str) -> None:
        await self._run("apply", "--filename", "-", stdin=manifest)

    async def delete(self, manifest: str) -> None:
        await self._run(
            "delete",
            "--ignore-not-found=true",
            "--wait=true",
            "--timeout=60s",
            "--filename",
            "-",
            stdin=manifest,
        )

    async def _run(self, *arguments: str, stdin: str | None = None) -> str:
        process = await asyncio.create_subprocess_exec(
            self._binary,
            "--context",
            self._context,
            *arguments,
            stdin=asyncio.subprocess.PIPE if stdin is not None else None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate(stdin.encode() if stdin is not None else None)
        if process.returncode != 0:
            message = stderr.decode(errors="replace").strip()
            raise KubectlError(f"kubectl command failed: {message}")
        return stdout.decode(errors="replace")

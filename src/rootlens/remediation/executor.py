"""Narrow remediation executors with no shell or arbitrary-command surface."""

from __future__ import annotations

import asyncio
from typing import Protocol

from rootlens.remediation.contracts import RemediationPlan


class RemediationExecutor(Protocol):
    name: str

    async def restart_pod(self, plan: RemediationPlan) -> str: ...


class DisabledRemediationExecutor:
    name = "disabled"

    async def restart_pod(self, plan: RemediationPlan) -> str:
        raise RuntimeError("remediation execution is disabled by configuration")


class KubectlPodRestartExecutor:
    """Execute only `kubectl delete pod` using validated, positional arguments."""

    name = "kubectl-delete-pod-v1"

    def __init__(self, *, kubectl_path: str, context: str) -> None:
        self._kubectl_path = kubectl_path
        self._context = context

    async def restart_pod(self, plan: RemediationPlan) -> str:
        process = await asyncio.create_subprocess_exec(
            self._kubectl_path,
            "--context",
            self._context,
            "delete",
            "pod",
            plan.target,
            "--namespace",
            plan.namespace,
            "--wait=false",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=30)
        except TimeoutError:
            process.kill()
            await process.wait()
            raise RuntimeError("pod restart timed out") from None
        if process.returncode != 0:
            message = stderr.decode(errors="replace").strip()[:500]
            raise RuntimeError(f"kubectl rejected pod restart: {message}")
        return stdout.decode(errors="replace").strip()[:500]

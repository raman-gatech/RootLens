"""Fail-safe experiment lifecycle with isolated ground-truth journaling."""

import asyncio
from datetime import UTC, datetime
from typing import Protocol

from experiment_controller.contracts import (
    ExperimentSpec,
    GroundTruthEvent,
    GroundTruthEventType,
    PublicExperimentReceipt,
)
from experiment_controller.ground_truth import GroundTruthJournal
from experiment_controller.manifests import manifest_digest, manifest_yaml


class ExperimentRunner(Protocol):
    async def require_target(self, spec: ExperimentSpec) -> None: ...

    async def server_dry_run(self, manifest: str) -> None: ...

    async def apply(self, manifest: str) -> None: ...

    async def delete(self, manifest: str) -> None: ...


class ExperimentController:
    def __init__(self, *, runner: ExperimentRunner, journal: GroundTruthJournal) -> None:
        self._runner = runner
        self._journal = journal

    async def validate(self, spec: ExperimentSpec) -> None:
        manifest = manifest_yaml(spec)
        await self._runner.require_target(spec)
        await self._runner.server_dry_run(manifest)

    async def run(self, spec: ExperimentSpec) -> PublicExperimentReceipt:
        manifest = manifest_yaml(spec)
        digest = manifest_digest(manifest)
        started_at = datetime.now(UTC)
        self._record(GroundTruthEventType.PLANNED, spec, digest)
        applied = False
        try:
            await self._runner.require_target(spec)
            await self._runner.apply(manifest)
            applied = True
            self._record(GroundTruthEventType.APPLIED, spec, digest)
            await asyncio.sleep(spec.duration_seconds)
        except BaseException as error:
            self._record(GroundTruthEventType.FAILED, spec, digest, type(error).__name__)
            raise
        finally:
            if applied:
                try:
                    await self._runner.delete(manifest)
                except BaseException as error:
                    self._record(
                        GroundTruthEventType.FAILED,
                        spec,
                        digest,
                        f"cleanup:{type(error).__name__}",
                    )
                    raise

        finished_at = datetime.now(UTC)
        self._record(GroundTruthEventType.RECOVERED, spec, digest)
        return PublicExperimentReceipt(
            experiment_id=spec.experiment_id,
            status=GroundTruthEventType.RECOVERED,
            started_at=started_at,
            finished_at=finished_at,
        )

    def _record(
        self,
        event: GroundTruthEventType,
        spec: ExperimentSpec,
        digest: str,
        detail: str | None = None,
    ) -> None:
        self._journal.append(
            GroundTruthEvent(
                event=event,
                spec=spec,
                manifest_sha256=digest,
                detail=detail,
            )
        )

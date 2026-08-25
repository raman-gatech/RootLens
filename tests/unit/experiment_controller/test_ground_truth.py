"""Ground-truth isolation and controller lifecycle tests."""

import asyncio
import stat
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from experiment_controller.catalog import scenario
from experiment_controller.contracts import FaultType, GroundTruthEvent
from experiment_controller.controller import ExperimentController
from experiment_controller.ground_truth import GroundTruthJournal


class FakeRunner:
    def __init__(self) -> None:
        self.operations: list[str] = []

    async def require_target(self, _: object) -> None:
        self.operations.append("target")

    async def server_dry_run(self, _: str) -> None:
        self.operations.append("dry-run")

    async def apply(self, _: str) -> None:
        self.operations.append("apply")

    async def delete(self, _: str) -> None:
        self.operations.append("delete")


class FailingDeleteRunner(FakeRunner):
    async def delete(self, manifest: str) -> None:
        await super().delete(manifest)
        raise RuntimeError("simulated cleanup failure")


async def test_controller_journals_truth_and_returns_redacted_receipt(
    tmp_path: Path,
    monkeypatch: object,
) -> None:
    sleep = AsyncMock()
    monkeypatch.setattr(asyncio, "sleep", sleep)  # type: ignore[attr-defined]
    runner = FakeRunner()
    journal = GroundTruthJournal(tmp_path / "isolated")
    controller = ExperimentController(runner=runner, journal=journal)
    spec = scenario(FaultType.CPU_STRESS, duration_seconds=5)

    receipt = await controller.run(spec)

    assert runner.operations == ["target", "apply", "delete"]
    sleep.assert_awaited_once_with(5)
    assert "fault_type" not in receipt.model_dump()
    assert "target_service" not in receipt.model_dump()
    events = [
        GroundTruthEvent.model_validate_json(line) for line in journal.path.read_text().splitlines()
    ]
    assert [event.event.value for event in events] == ["planned", "applied", "recovered"]
    assert all(event.spec == spec for event in events)
    assert stat.S_IMODE(journal.directory.stat().st_mode) == 0o700
    assert stat.S_IMODE(journal.path.stat().st_mode) == 0o600


async def test_controller_records_cleanup_failure_and_never_claims_recovery(
    tmp_path: Path,
    monkeypatch: object,
) -> None:
    monkeypatch.setattr(asyncio, "sleep", AsyncMock())  # type: ignore[attr-defined]
    journal = GroundTruthJournal(tmp_path / "isolated")
    controller = ExperimentController(runner=FailingDeleteRunner(), journal=journal)

    with pytest.raises(RuntimeError, match="simulated cleanup failure"):
        await controller.run(scenario(FaultType.POD_KILL, duration_seconds=5))

    events = [
        GroundTruthEvent.model_validate_json(line) for line in journal.path.read_text().splitlines()
    ]
    assert [event.event.value for event in events] == ["planned", "applied", "failed"]
    assert events[-1].detail == "cleanup:RuntimeError"


def test_ground_truth_is_absent_from_the_rootlens_runtime_boundary() -> None:
    project = Path(__file__).resolve().parents[3]
    dockerfile = (project / "Dockerfile").read_text(encoding="utf-8")
    compose = (project / "compose.yaml").read_text(encoding="utf-8")

    assert "experiment_controller" not in dockerfile
    assert "ground-truth" not in dockerfile
    assert "ground-truth" not in compose

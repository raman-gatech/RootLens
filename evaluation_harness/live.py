"""Blind live-fault evaluation against a running RootLens API."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path
from time import perf_counter
from typing import Any
from uuid import UUID

import httpx

from evaluation_harness.contracts import TrialResult
from evaluation_harness.runner import aggregate_trials
from experiment_controller.catalog import scenario
from experiment_controller.contracts import FaultType, GroundTruthEventType
from experiment_controller.controller import ExperimentController
from experiment_controller.ground_truth import GroundTruthJournal
from experiment_controller.kubectl import KubectlRunner
from rootlens.evaluation import EvaluationReport
from rootlens.investigation import Incident, Investigation

ProgressCallback = Callable[[int, int], None]


class LiveEvaluationError(RuntimeError):
    """Raised when a live benchmark case cannot be completed safely."""


class RootLensClient:
    def __init__(
        self,
        *,
        base_url: str,
        token: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers=headers,
            timeout=httpx.Timeout(180),
            transport=transport,
        )

    async def __aenter__(self) -> RootLensClient:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self._client.aclose()

    async def create_blind_incident(
        self, *, ordinal: int, started_at: Any, finished_at: Any
    ) -> Incident:
        response = await self._client.post(
            "/api/v1/incidents",
            json={
                "title": "Customer request degradation",
                "summary": "Automated blind evaluation incident detected from live telemetry.",
                "affected_service": "frontend-proxy",
                "severity": "sev2",
                "incident_start": (started_at - timedelta(minutes=2)).isoformat(),
                "incident_end": finished_at.isoformat(),
                "labels": {"dataset": "rootlens-chaos-live-v1", "ordinal": str(ordinal)},
            },
        )
        response.raise_for_status()
        return Incident.model_validate(response.json())

    async def investigate(self, incident_id: UUID) -> Investigation:
        started = perf_counter()
        response = await self._client.post(
            f"/api/v1/incidents/{incident_id}/investigate",
            json={"mode": "multi_agent"},
        )
        response.raise_for_status()
        investigation = Investigation.model_validate(response.json())
        if investigation.completed_at is None:
            raise LiveEvaluationError("RootLens returned an incomplete investigation")
        investigation_latency_ms = (perf_counter() - started) * 1_000
        return investigation.model_copy(
            update={
                "usage": investigation.usage.model_copy(
                    update={"wall_time_seconds": investigation_latency_ms / 1_000}
                )
            }
        )

    async def publish(self, report: EvaluationReport) -> None:
        response = await self._client.post(
            "/api/v1/evaluations",
            content=report.model_dump_json(),
            headers={"Content-Type": "application/json"},
        )
        response.raise_for_status()


async def run_live_evaluation(
    *,
    context: str,
    base_url: str,
    ground_truth_directory: Path,
    repetitions: int = 5,
    duration_seconds: int = 5,
    settle_seconds: float = 2,
    token: str | None = None,
    publish: bool = False,
    progress: ProgressCallback | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> EvaluationReport:
    """Run every fault family and expose only aggregate RootLens accuracy."""
    if not 1 <= repetitions <= 20:
        raise ValueError("repetitions must be between 1 and 20")
    if not 5 <= duration_seconds <= 600:
        raise ValueError("duration_seconds must be between 5 and 600")
    if not 0 <= settle_seconds <= 60:
        raise ValueError("settle_seconds must be between 0 and 60")

    controller = ExperimentController(
        runner=KubectlRunner(context=context),
        journal=GroundTruthJournal(ground_truth_directory),
    )
    trials: list[TrialResult] = []
    total = len(FaultType) * repetitions
    async with RootLensClient(base_url=base_url, token=token, transport=transport) as client:
        ordinal = 0
        for repetition in range(1, repetitions + 1):
            for fault_type in FaultType:
                ordinal += 1
                spec = scenario(fault_type, duration_seconds=duration_seconds)
                receipt = await controller.run(spec)
                if receipt.status is not GroundTruthEventType.RECOVERED or not receipt.finished_at:
                    raise LiveEvaluationError("fault lifecycle did not reach recovery")
                if settle_seconds:
                    await asyncio.sleep(settle_seconds)
                incident = await client.create_blind_incident(
                    ordinal=ordinal,
                    started_at=receipt.started_at,
                    finished_at=receipt.finished_at,
                )
                investigation = await client.investigate(incident.id)
                trials.append(
                    _trial(
                        ordinal=ordinal,
                        repetition=repetition,
                        ground_truth=spec.target_service,
                        investigation=investigation,
                    )
                )
                if progress:
                    progress(ordinal, total)

        report = EvaluationReport(
            dataset_version="rootlens-chaos-live-v1",
            execution_mode="live",
            fault_type_count=len(FaultType),
            repetitions_per_fault=repetitions,
            incident_count=len(trials),
            methods={"E_rootlens": aggregate_trials(tuple(trials))},
            ablations={},
            notes=(
                "Each trial required Chaos Mesh AllInjected=True and a recovered lifecycle.",
                "RootLens received generic incident metadata without fault type or target service.",
                "Published output excludes per-case predictions and hidden ground truth.",
            ),
        )
        if publish:
            await client.publish(report)
        return report


def _trial(
    *, ordinal: int, repetition: int, ground_truth: str, investigation: Investigation
) -> TrialResult:
    claimed = tuple(
        evidence_id
        for hypothesis in investigation.hypotheses[:3]
        for evidence_id in hypothesis.evidence_for
    )
    return TrialResult(
        case_id=f"live-{repetition:02d}-{ordinal:03d}",
        method="E_rootlens",
        predictions=tuple(item.root_cause_service for item in investigation.hypotheses),
        claimed_evidence_ids=claimed,
        valid_evidence_ids=tuple(item.id for item in investigation.evidence),
        latency_ms=investigation.usage.wall_time_seconds * 1_000,
        tool_calls=investigation.usage.tool_calls,
        llm_calls=investigation.usage.llm_calls,
        input_tokens=investigation.usage.input_tokens,
        output_tokens=investigation.usage.output_tokens,
        estimated_cost_usd=investigation.usage.estimated_cost_usd,
        safety_violations=0,
        ground_truth=ground_truth,
    )

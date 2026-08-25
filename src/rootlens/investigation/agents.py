"""Single-agent baseline and manager-mediated specialist orchestration."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from time import monotonic
from uuid import UUID, uuid4

from rootlens.investigation.causal import CausalRanker
from rootlens.investigation.contracts import (
    AgentMode,
    AgentRole,
    AgentRun,
    EvidenceBundle,
    Incident,
    Investigation,
    InvestigationBudget,
    InvestigationStatus,
    InvestigationUsage,
)
from rootlens.investigation.memory import IncidentMemory
from rootlens.investigation.provider import HypothesisProvider
from rootlens.investigation.tools import EvidenceToolbox
from rootlens.investigation.verifier import EvidenceVerifier


class InvestigationRunner:
    def __init__(
        self,
        *,
        toolbox: EvidenceToolbox,
        provider: HypothesisProvider,
        ranker: CausalRanker | None = None,
        verifier: EvidenceVerifier | None = None,
        memory: IncidentMemory | None = None,
    ) -> None:
        self._toolbox = toolbox
        self._provider = provider
        self._ranker = ranker or CausalRanker()
        self._verifier = verifier or EvidenceVerifier()
        self._memory = memory

    async def run(
        self,
        incident: Incident,
        *,
        mode: AgentMode,
        budget: InvestigationBudget | None = None,
    ) -> Investigation:
        investigation_id = uuid4()
        limits = budget or InvestigationBudget()
        started_at = datetime.now(UTC)
        timer = monotonic()
        required_tools = 4 + int(mode is AgentMode.MULTI and self._memory is not None)
        if limits.max_tool_calls < required_tools:
            return Investigation(
                id=investigation_id,
                incident_id=incident.id,
                mode=mode,
                provider=self._provider.name,
                status=InvestigationStatus.BUDGET_EXHAUSTED,
                started_at=started_at,
                completed_at=datetime.now(UTC),
                budget=limits,
                warnings=("tool budget is smaller than the selected fixed tool plan",),
            )
        try:
            if mode is AgentMode.SINGLE:
                bundles, agent_runs = await asyncio.wait_for(
                    self._single(incident, investigation_id),
                    timeout=limits.max_duration_seconds,
                )
                generated_by = AgentRole.SINGLE
            else:
                bundles, agent_runs = await asyncio.wait_for(
                    self._multi(incident, investigation_id),
                    timeout=limits.max_duration_seconds,
                )
                generated_by = AgentRole.MANAGER
        except TimeoutError:
            return Investigation(
                id=investigation_id,
                incident_id=incident.id,
                mode=mode,
                provider=self._provider.name,
                status=InvestigationStatus.BUDGET_EXHAUSTED,
                started_at=started_at,
                completed_at=datetime.now(UTC),
                budget=limits,
                warnings=("duration budget exhausted during evidence collection",),
            )

        if mode is AgentMode.MULTI and self._memory is not None:
            current_evidence = tuple(item for bundle in bundles for item in bundle.evidence)
            memory_started = datetime.now(UTC)
            remaining = max(0.001, limits.max_duration_seconds - (monotonic() - timer))
            try:
                memory_bundle = await asyncio.wait_for(
                    self._memory.evidence_bundle(incident, investigation_id, current_evidence),
                    timeout=remaining,
                )
            except TimeoutError:
                return Investigation(
                    id=investigation_id,
                    incident_id=incident.id,
                    mode=mode,
                    provider=self._provider.name,
                    status=InvestigationStatus.BUDGET_EXHAUSTED,
                    started_at=started_at,
                    completed_at=datetime.now(UTC),
                    budget=limits,
                    evidence=current_evidence,
                    warnings=("duration budget exhausted during memory retrieval",),
                )
            bundles = (*bundles, memory_bundle)
            agent_runs = (
                *agent_runs,
                AgentRun(
                    agent_id=AgentRole.MEMORY,
                    started_at=memory_started,
                    completed_at=datetime.now(UTC),
                    status="completed",
                    input_evidence_ids=tuple(item.id for item in current_evidence),
                    notes=("historical matches labeled as non-factual priors",),
                ),
            )

        evidence = tuple(item for bundle in bundles for item in bundle.evidence)
        tool_calls = tuple(item for bundle in bundles for item in bundle.tool_calls)
        warnings = tuple(item for bundle in bundles for item in bundle.warnings)
        graph = next((bundle.graph for bundle in bundles if bundle.graph is not None), None)
        if len(tool_calls) > limits.max_tool_calls:
            return Investigation(
                id=investigation_id,
                incident_id=incident.id,
                mode=mode,
                provider=self._provider.name,
                status=InvestigationStatus.BUDGET_EXHAUSTED,
                started_at=started_at,
                completed_at=datetime.now(UTC),
                budget=limits,
                evidence=evidence,
                tool_calls=tool_calls[: limits.max_tool_calls],
                graph=graph,
                warnings=(*warnings, "tool-call budget exhausted"),
            )

        synthesis_started = datetime.now(UTC)
        if self._provider.name.startswith("openai-") and limits.max_llm_calls == 0:
            return Investigation(
                id=investigation_id,
                incident_id=incident.id,
                mode=mode,
                provider=self._provider.name,
                status=InvestigationStatus.BUDGET_EXHAUSTED,
                started_at=started_at,
                completed_at=datetime.now(UTC),
                budget=limits,
                evidence=evidence,
                tool_calls=tool_calls,
                graph=graph,
                warnings=("model-call budget forbids the configured provider",),
            )
        remaining = max(0.001, limits.max_duration_seconds - (monotonic() - timer))
        try:
            result = await asyncio.wait_for(
                self._provider.synthesize(incident, evidence, generated_by=generated_by),
                timeout=remaining,
            )
        except TimeoutError:
            return Investigation(
                id=investigation_id,
                incident_id=incident.id,
                mode=mode,
                provider=self._provider.name,
                status=InvestigationStatus.BUDGET_EXHAUSTED,
                started_at=started_at,
                completed_at=datetime.now(UTC),
                budget=limits,
                evidence=evidence,
                tool_calls=tool_calls,
                graph=graph,
                warnings=("duration budget exhausted during synthesis",),
            )
        hypotheses = self._ranker.rank(result.hypotheses, evidence, incident, graph)
        manager_finished = datetime.now(UTC)
        agent_runs = (
            *agent_runs,
            AgentRun(
                agent_id=generated_by,
                started_at=synthesis_started,
                completed_at=manager_finished,
                status="completed",
                input_evidence_ids=tuple(item.id for item in evidence),
                output_hypothesis_ids=tuple(item.id for item in hypotheses),
                notes=("deterministic causal ranking applied",),
            ),
        )
        if mode is AgentMode.MULTI:
            verifier_started = datetime.now(UTC)
            hypotheses = self._verifier.verify(hypotheses, evidence)
            agent_runs = (
                *agent_runs,
                AgentRun(
                    agent_id=AgentRole.VERIFIER,
                    started_at=verifier_started,
                    completed_at=datetime.now(UTC),
                    status="completed",
                    input_evidence_ids=tuple(item.id for item in evidence),
                    output_hypothesis_ids=tuple(item.id for item in hypotheses),
                    notes=("unsupported references removed; contradictions checked",),
                ),
            )
        wall_time = monotonic() - timer
        usage = result.usage.model_copy(
            update={
                "tool_calls": len(tool_calls),
                "telemetry_bytes": sum(item.result_bytes for item in tool_calls),
                "wall_time_seconds": wall_time,
            }
        )
        status = (
            InvestigationStatus.BUDGET_EXHAUSTED
            if wall_time > limits.max_duration_seconds
            else InvestigationStatus.COMPLETED
        )
        return Investigation(
            id=investigation_id,
            incident_id=incident.id,
            mode=mode,
            provider=result.provider,
            status=status,
            started_at=started_at,
            completed_at=datetime.now(UTC),
            budget=limits,
            usage=InvestigationUsage.model_validate(usage),
            evidence=evidence,
            hypotheses=hypotheses,
            agent_runs=agent_runs,
            tool_calls=tool_calls,
            graph=graph,
            warnings=warnings,
        )

    async def _single(
        self, incident: Incident, investigation_id: UUID
    ) -> tuple[tuple[EvidenceBundle, ...], tuple[AgentRun, ...]]:
        started = datetime.now(UTC)
        bundles = (
            await self._toolbox.metrics(incident, investigation_id, AgentRole.SINGLE),
            await self._toolbox.traces(incident, investigation_id, AgentRole.SINGLE),
            await self._toolbox.logs(incident, investigation_id, AgentRole.SINGLE),
            await self._toolbox.changes(incident, investigation_id, AgentRole.SINGLE),
        )
        run = AgentRun(
            agent_id=AgentRole.SINGLE,
            started_at=started,
            completed_at=datetime.now(UTC),
            status="completed",
            input_evidence_ids=(),
            notes=("evidence tools executed sequentially",),
        )
        return bundles, (run,)

    async def _multi(
        self, incident: Incident, investigation_id: UUID
    ) -> tuple[tuple[EvidenceBundle, ...], tuple[AgentRun, ...]]:
        starts = {role: datetime.now(UTC) for role in _SPECIALISTS}
        bundles = await asyncio.gather(
            self._toolbox.metrics(incident, investigation_id, AgentRole.METRICS),
            self._toolbox.traces(incident, investigation_id, AgentRole.TRACES),
            self._toolbox.logs(incident, investigation_id, AgentRole.LOGS),
            self._toolbox.changes(incident, investigation_id, AgentRole.CHANGES),
        )
        finished = datetime.now(UTC)
        runs = tuple(
            AgentRun(
                agent_id=bundle.agent,
                started_at=starts[bundle.agent],
                completed_at=finished,
                status="completed" if not bundle.warnings else "failed",
                output_hypothesis_ids=(),
                notes=bundle.warnings,
            )
            for bundle in bundles
        )
        return tuple(bundles), runs


_SPECIALISTS = (
    AgentRole.METRICS,
    AgentRole.TRACES,
    AgentRole.LOGS,
    AgentRole.CHANGES,
)

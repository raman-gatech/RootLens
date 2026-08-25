"""Single- and multi-agent orchestration tests."""

import asyncio
from datetime import UTC, datetime, timedelta
from time import monotonic
from uuid import UUID

from rootlens.investigation.agents import InvestigationRunner
from rootlens.investigation.contracts import (
    AgentMode,
    AgentRole,
    Evidence,
    EvidenceBundle,
    EvidenceSource,
    Incident,
    InvestigationBudget,
    InvestigationStatus,
)
from rootlens.investigation.provider import DeterministicHypothesisProvider
from rootlens.telemetry import QueryWindow


class FakeToolbox:
    async def metrics(
        self, incident: Incident, investigation_id: UUID, agent: AgentRole
    ) -> EvidenceBundle:
        return await self._collect(incident, agent, EvidenceSource.METRICS)

    async def traces(
        self, incident: Incident, investigation_id: UUID, agent: AgentRole
    ) -> EvidenceBundle:
        return await self._collect(incident, agent, EvidenceSource.TRACES)

    async def logs(
        self, incident: Incident, investigation_id: UUID, agent: AgentRole
    ) -> EvidenceBundle:
        return await self._collect(incident, agent, EvidenceSource.LOGS)

    async def changes(
        self, incident: Incident, investigation_id: UUID, agent: AgentRole
    ) -> EvidenceBundle:
        return await self._collect(incident, agent, EvidenceSource.CHANGES)

    async def _collect(
        self, incident: Incident, agent: AgentRole, source: EvidenceSource
    ) -> EvidenceBundle:
        await asyncio.sleep(0.03)
        item = Evidence(
            source=source,
            service="checkout",
            signal=source.value,
            observation=f"{source.value} observation",
            window=incident.window,
            query_reference=f"telemetry://{source.value}/test",
            confidence=0.8,
            attributes={"anomaly_score": 0.8} if source is EvidenceSource.METRICS else {},
        )
        return EvidenceBundle(agent=agent, evidence=(item,), tool_calls=())


async def test_multi_agent_collectors_run_concurrently_and_verifier_runs() -> None:
    runner = InvestigationRunner(
        toolbox=FakeToolbox(),  # type: ignore[arg-type]
        provider=DeterministicHypothesisProvider(),
    )
    started = monotonic()

    result = await runner.run(_incident(), mode=AgentMode.MULTI)

    elapsed = monotonic() - started
    assert elapsed < 0.09
    assert result.status is InvestigationStatus.COMPLETED
    assert {run.agent_id for run in result.agent_runs} >= {
        AgentRole.METRICS,
        AgentRole.TRACES,
        AgentRole.LOGS,
        AgentRole.CHANGES,
        AgentRole.MANAGER,
        AgentRole.VERIFIER,
    }
    assert result.hypotheses[0].evidence_for


async def test_single_agent_collects_sequentially_without_specialists() -> None:
    runner = InvestigationRunner(
        toolbox=FakeToolbox(),  # type: ignore[arg-type]
        provider=DeterministicHypothesisProvider(),
    )
    started = monotonic()

    result = await runner.run(_incident(), mode=AgentMode.SINGLE)

    assert monotonic() - started >= 0.11
    assert {run.agent_id for run in result.agent_runs} == {AgentRole.SINGLE}
    assert result.hypotheses[0].generated_by is AgentRole.SINGLE


async def test_fixed_tool_plan_respects_budget_before_calling_tools() -> None:
    runner = InvestigationRunner(
        toolbox=FakeToolbox(),  # type: ignore[arg-type]
        provider=DeterministicHypothesisProvider(),
    )

    result = await runner.run(
        _incident(),
        mode=AgentMode.MULTI,
        budget=InvestigationBudget(max_tool_calls=3),
    )

    assert result.status is InvestigationStatus.BUDGET_EXHAUSTED
    assert result.tool_calls == ()
    assert result.evidence == ()


def _incident() -> Incident:
    start = datetime(2026, 8, 25, 12, tzinfo=UTC)
    return Incident(
        title="Checkout incident",
        affected_service="frontend",
        window=QueryWindow(start=start, end=start + timedelta(minutes=5)),
    )

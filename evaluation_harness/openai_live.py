"""Real OpenAI comparison methods for blinded live-fault evaluation."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import dataclass
from time import perf_counter
from uuid import UUID

from evaluation_harness.contracts import TrialResult
from rootlens.investigation import Evidence, EvidenceSource, Hypothesis, Incident, Investigation
from rootlens.investigation.causal import CausalRanker
from rootlens.investigation.contracts import AgentRole, InvestigationUsage
from rootlens.investigation.provider import HypothesisProvider, ProviderResult
from rootlens.investigation.verifier import EvidenceVerifier

DEFAULT_OPENAI_MODEL = "gpt-5.4-mini-2026-03-17"
OPENAI_METHODS = (
    "A_alert_only",
    "B_single_llm",
    "C_retrieval_agent",
    "D_multi_agent",
    "E_rootlens",
)

_PRICE_PER_MILLION_TOKENS = {
    "gpt-5.4-mini": (0.75, 4.50),
    DEFAULT_OPENAI_MODEL: (0.75, 4.50),
}
_SPECIALISTS: tuple[tuple[AgentRole, frozenset[EvidenceSource]], ...] = (
    (AgentRole.METRICS, frozenset({EvidenceSource.METRICS})),
    (AgentRole.TRACES, frozenset({EvidenceSource.TRACES})),
    (AgentRole.LOGS, frozenset({EvidenceSource.LOGS})),
    (
        AgentRole.CHANGES,
        frozenset(
            {
                EvidenceSource.CHANGES,
                EvidenceSource.KUBERNETES,
                EvidenceSource.TOPOLOGY,
                EvidenceSource.MEMORY,
            }
        ),
    ),
)


@dataclass(frozen=True)
class _TimedResult:
    result: ProviderResult
    latency_ms: float


class OpenAILiveBaselineSuite:
    """Run five comparable methods without exposing case labels to the model."""

    def __init__(self, *, provider: HypothesisProvider, model: str) -> None:
        if model not in _PRICE_PER_MILLION_TOKENS:
            raise ValueError(f"no audited price is configured for OpenAI model {model!r}")
        self._provider = provider
        self._model = model
        self._ranker = CausalRanker()
        self._verifier = EvidenceVerifier()

    @property
    def model(self) -> str:
        return self._model

    async def run(
        self,
        *,
        incident: Incident,
        investigation: Investigation,
        ground_truth: str,
        case_id: str,
    ) -> dict[str, TrialResult]:
        """Generate predictions first, then attach private truth for aggregation."""
        evidence = investigation.evidence
        specialist_groups = tuple(
            (
                role,
                tuple(item for item in evidence if item.source in sources),
            )
            for role, sources in _SPECIALISTS
        )
        specialist_groups = tuple(item for item in specialist_groups if item[1])

        alert_task = _timed_synthesize(
            self._provider,
            incident,
            (),
            generated_by=AgentRole.SINGLE,
        )
        retrieval_task = _timed_synthesize(
            self._provider,
            incident,
            evidence,
            generated_by=AgentRole.SINGLE,
        )
        specialists_task = _run_specialists(self._provider, incident, specialist_groups)
        alert_result, retrieval_result, specialist_results = await asyncio.gather(
            alert_task, retrieval_task, specialists_task
        )

        specialist_hypotheses = _merge_hypotheses(
            tuple(
                hypothesis for timed in specialist_results for hypothesis in timed.result.hypotheses
            )
        )
        specialist_usage = _sum_usage(tuple(item.result.usage for item in specialist_results))
        specialist_latency_ms = max((item.latency_ms for item in specialist_results), default=0.0)

        rootlens_started = perf_counter()
        ranked = self._ranker.rank(
            specialist_hypotheses,
            evidence,
            incident,
            investigation.graph,
        )
        verified = self._verifier.verify(ranked, evidence)
        rootlens_latency_ms = specialist_latency_ms + (perf_counter() - rootlens_started) * 1_000

        valid_evidence_ids = tuple(item.id for item in evidence)
        tool_calls = investigation.usage.tool_calls
        return {
            "A_alert_only": _trial(
                case_id=case_id,
                method="A_alert_only",
                predictions=(incident.affected_service or "unknown",),
                hypotheses=(),
                valid_evidence_ids=valid_evidence_ids,
                ground_truth=ground_truth,
                latency_ms=0,
                tool_calls=0,
                usage=InvestigationUsage(),
                estimated_cost_usd=0,
            ),
            "B_single_llm": _provider_trial(
                case_id=case_id,
                method="B_single_llm",
                timed=alert_result,
                valid_evidence_ids=valid_evidence_ids,
                ground_truth=ground_truth,
                tool_calls=0,
                model=self._model,
            ),
            "C_retrieval_agent": _provider_trial(
                case_id=case_id,
                method="C_retrieval_agent",
                timed=retrieval_result,
                valid_evidence_ids=valid_evidence_ids,
                ground_truth=ground_truth,
                tool_calls=tool_calls,
                model=self._model,
            ),
            "D_multi_agent": _trial(
                case_id=case_id,
                method="D_multi_agent",
                predictions=tuple(item.root_cause_service for item in specialist_hypotheses),
                hypotheses=specialist_hypotheses,
                valid_evidence_ids=valid_evidence_ids,
                ground_truth=ground_truth,
                latency_ms=specialist_latency_ms,
                tool_calls=tool_calls,
                usage=specialist_usage,
                estimated_cost_usd=_estimated_cost(specialist_usage, self._model),
            ),
            "E_rootlens": _trial(
                case_id=case_id,
                method="E_rootlens",
                predictions=tuple(item.root_cause_service for item in verified),
                hypotheses=verified,
                valid_evidence_ids=valid_evidence_ids,
                ground_truth=ground_truth,
                latency_ms=rootlens_latency_ms,
                tool_calls=tool_calls,
                usage=specialist_usage,
                estimated_cost_usd=_estimated_cost(specialist_usage, self._model),
            ),
        }


async def _timed_synthesize(
    provider: HypothesisProvider,
    incident: Incident,
    evidence: tuple[Evidence, ...],
    *,
    generated_by: AgentRole,
) -> _TimedResult:
    started = perf_counter()
    result = await provider.synthesize(incident, evidence, generated_by=generated_by)
    return _TimedResult(result=result, latency_ms=(perf_counter() - started) * 1_000)


async def _run_specialists(
    provider: HypothesisProvider,
    incident: Incident,
    groups: tuple[tuple[AgentRole, tuple[Evidence, ...]], ...],
) -> tuple[_TimedResult, ...]:
    return tuple(
        await asyncio.gather(
            *(
                _timed_synthesize(provider, incident, evidence, generated_by=role)
                for role, evidence in groups
            )
        )
    )


def _merge_hypotheses(hypotheses: tuple[Hypothesis, ...]) -> tuple[Hypothesis, ...]:
    by_service: dict[str, list[Hypothesis]] = defaultdict(list)
    for hypothesis in hypotheses:
        by_service[hypothesis.root_cause_service].append(hypothesis)

    merged: list[Hypothesis] = []
    for service, candidates in by_service.items():
        candidates.sort(key=lambda item: (-item.confidence, item.id))
        strongest = candidates[0]
        supporting = tuple(dict.fromkeys(item for row in candidates for item in row.evidence_for))
        opposing = tuple(dict.fromkeys(item for row in candidates for item in row.evidence_against))
        merged.append(
            strongest.model_copy(
                update={
                    "id": f"service:{service}",
                    "evidence_for": supporting,
                    "evidence_against": opposing,
                }
            )
        )
    merged.sort(key=lambda item: (-item.confidence, item.root_cause_service, item.id))
    return tuple(item.model_copy(update={"rank": rank}) for rank, item in enumerate(merged[:5], 1))


def _provider_trial(
    *,
    case_id: str,
    method: str,
    timed: _TimedResult,
    valid_evidence_ids: tuple[UUID, ...],
    ground_truth: str,
    tool_calls: int,
    model: str,
) -> TrialResult:
    hypotheses = timed.result.hypotheses
    return _trial(
        case_id=case_id,
        method=method,
        predictions=tuple(item.root_cause_service for item in hypotheses),
        hypotheses=hypotheses,
        valid_evidence_ids=valid_evidence_ids,
        ground_truth=ground_truth,
        latency_ms=timed.latency_ms,
        tool_calls=tool_calls,
        usage=timed.result.usage,
        estimated_cost_usd=_estimated_cost(timed.result.usage, model),
    )


def _trial(
    *,
    case_id: str,
    method: str,
    predictions: tuple[str, ...],
    hypotheses: tuple[Hypothesis, ...],
    valid_evidence_ids: tuple[UUID, ...],
    ground_truth: str,
    latency_ms: float,
    tool_calls: int,
    usage: InvestigationUsage,
    estimated_cost_usd: float,
) -> TrialResult:
    claims = tuple(
        evidence_id for hypothesis in hypotheses[:3] for evidence_id in hypothesis.evidence_for
    )
    return TrialResult(
        case_id=case_id,
        method=method,
        predictions=predictions,
        claimed_evidence_ids=claims,
        valid_evidence_ids=valid_evidence_ids,
        latency_ms=latency_ms,
        tool_calls=tool_calls,
        llm_calls=usage.llm_calls,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        estimated_cost_usd=estimated_cost_usd,
        safety_violations=0,
        ground_truth=ground_truth,
    )


def _sum_usage(items: tuple[InvestigationUsage, ...]) -> InvestigationUsage:
    return InvestigationUsage(
        llm_calls=sum(item.llm_calls for item in items),
        input_tokens=sum(item.input_tokens for item in items),
        output_tokens=sum(item.output_tokens for item in items),
    )


def _estimated_cost(usage: InvestigationUsage, model: str) -> float:
    input_price, output_price = _PRICE_PER_MILLION_TOKENS[model]
    return round(
        usage.input_tokens * input_price / 1_000_000
        + usage.output_tokens * output_price / 1_000_000,
        9,
    )

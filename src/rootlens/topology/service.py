"""Application service coordinating trace collection, graph building, and storage."""

import asyncio

from rootlens.telemetry import QueryWindow, TelemetryEnvelope, TelemetryGateway
from rootlens.telemetry.contracts import SpanRecord, TraceSummary
from rootlens.telemetry.errors import TelemetryQueryError
from rootlens.topology.builder import ServiceGraphBuilder
from rootlens.topology.contracts import ServiceGraphSnapshot
from rootlens.topology.errors import TopologyBuildError
from rootlens.topology.repository import ServiceGraphRepository


class ServiceTopologyService:
    def __init__(
        self,
        *,
        gateway: TelemetryGateway,
        repository: ServiceGraphRepository,
        builder: ServiceGraphBuilder | None = None,
        default_trace_limit: int = 100,
    ) -> None:
        self._gateway = gateway
        self._repository = repository
        self._builder = builder or ServiceGraphBuilder()
        self._default_trace_limit = default_trace_limit

    async def rebuild(
        self,
        window: QueryWindow,
        *,
        traceql: str = "{}",
        trace_limit: int | None = None,
    ) -> ServiceGraphSnapshot:
        resolved_limit = trace_limit or self._default_trace_limit
        search = await self._gateway.tempo.search_traces(
            traceql,
            window,
            limit=resolved_limit,
        )
        if not search.data:
            raise TopologyBuildError("Tempo returned no traces for the topology window")

        retrieved = await asyncio.gather(*(self._fetch_trace(summary) for summary in search.data))
        spans: list[SpanRecord] = []
        references = [search.provenance.reference]
        warnings: list[str] = []
        for trace, warning in retrieved:
            if trace is not None:
                spans.extend(trace.data)
                references.append(trace.provenance.reference)
            if warning is not None:
                warnings.append(warning)
        if not spans:
            raise TopologyBuildError(
                "no trace payload could be retrieved for topology reconstruction"
            )

        snapshot = self._builder.build(
            spans,
            window=window,
            evidence_references=references,
            warnings=warnings,
        )
        await self._repository.save(snapshot)
        return snapshot

    async def latest(self) -> ServiceGraphSnapshot | None:
        return await self._repository.latest()

    async def _fetch_trace(
        self,
        summary: TraceSummary,
    ) -> tuple[TelemetryEnvelope[list[SpanRecord]] | None, str | None]:
        try:
            return await self._gateway.tempo.get_trace(summary.trace_id), None
        except TelemetryQueryError as error:
            return None, f"trace {summary.trace_id} was skipped: {error}"

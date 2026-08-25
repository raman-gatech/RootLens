"""Incident-memory isolation and embedding tests."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from rootlens.investigation.contracts import (
    AgentRole,
    Evidence,
    EvidenceOrigin,
    EvidenceSource,
    HistoricalIncident,
    Incident,
    SimilarIncident,
)
from rootlens.investigation.memory import IncidentMemory, cosine, embed
from rootlens.telemetry import QueryWindow


class FakeMemoryRepository:
    def __init__(self) -> None:
        self.saved: HistoricalIncident | None = None

    async def save(self, incident: HistoricalIncident, embedding: tuple[float, ...]) -> None:
        self.saved = incident
        assert len(embedding) == 128

    async def search(
        self, embedding: tuple[float, ...], *, limit: int = 5
    ) -> tuple[SimilarIncident, ...]:
        historical = HistoricalIncident(
            title="Prior checkout timeout",
            root_cause_service="checkout",
            failure_mode="dependency timeout",
            resolution="restart checkout",
        )
        return (SimilarIncident(incident=historical, similarity=0.82),)


def test_feature_hash_embedding_is_stable_and_semantically_self_similar() -> None:
    first = embed("checkout latency timeout")
    second = embed("checkout latency timeout")
    unrelated = embed("advertising image rendering")

    assert first == second
    assert len(first) == 128
    assert cosine(first, second) == 1.0
    assert cosine(first, unrelated) < 0.5


async def test_retrieved_memory_is_explicitly_historical_prior() -> None:
    memory = IncidentMemory(FakeMemoryRepository())  # type: ignore[arg-type]
    incident = _incident()
    current = Evidence(
        source=EvidenceSource.METRICS,
        service="checkout",
        signal="latency",
        observation="checkout latency high",
        query_reference="telemetry://prometheus/test",
        confidence=0.9,
    )

    bundle = await memory.evidence_bundle(incident, UUID(int=2), (current,))

    assert bundle.agent is AgentRole.MEMORY
    assert bundle.evidence[0].origin is EvidenceOrigin.HISTORICAL_PRIOR
    assert "not current-incident evidence" in bundle.evidence[0].observation
    assert bundle.evidence[0].query_reference.startswith("memory://historical/")


def _incident() -> Incident:
    start = datetime(2026, 8, 25, 12, tzinfo=UTC)
    return Incident(
        title="Checkout timeout",
        window=QueryWindow(start=start, end=start + timedelta(minutes=5)),
    )

"""PostgreSQL/pgvector incident memory with strict historical-prior isolation."""

from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Iterable
from uuid import UUID

import sqlalchemy as sa

from rootlens.db.session import Database
from rootlens.investigation.contracts import (
    AgentRole,
    Evidence,
    EvidenceBundle,
    EvidenceOrigin,
    EvidenceSource,
    HistoricalIncident,
    Incident,
    SimilarIncident,
    ToolCallAudit,
)

_DIMENSIONS = 128
_TOKEN = re.compile(r"[a-z0-9][a-z0-9_.-]+")


class IncidentMemoryRepository:
    def __init__(self, database: Database) -> None:
        self._database = database

    async def save(self, incident: HistoricalIncident, embedding: tuple[float, ...]) -> None:
        statement = sa.text(
            """
            INSERT INTO historical_incidents
                (id, source_incident_id, created_at, root_cause_service, failure_mode,
                 embedding, payload)
            VALUES
                (:id, :source_incident_id, :created_at, :root_cause_service, :failure_mode,
                 CAST(:embedding AS vector), CAST(:payload AS json))
            """
        )
        async with self._database.session() as session:
            await session.execute(
                statement,
                {
                    "id": incident.id,
                    "source_incident_id": incident.source_incident_id,
                    "created_at": incident.created_at,
                    "root_cause_service": incident.root_cause_service,
                    "failure_mode": incident.failure_mode,
                    "embedding": _vector_literal(embedding),
                    "payload": incident.model_dump_json(),
                },
            )
            await session.commit()

    async def search(
        self, embedding: tuple[float, ...], *, limit: int = 5
    ) -> tuple[SimilarIncident, ...]:
        statement = sa.text(
            """
            SELECT payload, 1 - (embedding <=> CAST(:embedding AS vector)) AS similarity
            FROM historical_incidents
            ORDER BY embedding <=> CAST(:embedding AS vector), created_at DESC
            LIMIT :limit
            """
        )
        async with self._database.session() as session:
            result = await session.execute(
                statement, {"embedding": _vector_literal(embedding), "limit": limit}
            )
            rows = result.mappings().all()
        return tuple(
            SimilarIncident(
                incident=HistoricalIncident.model_validate(row["payload"]),
                similarity=max(-1.0, min(1.0, float(row["similarity"]))),
            )
            for row in rows
        )


class IncidentMemory:
    def __init__(self, repository: IncidentMemoryRepository) -> None:
        self._repository = repository

    async def remember(self, incident: HistoricalIncident) -> HistoricalIncident:
        await self._repository.save(incident, embed(_historical_text(incident)))
        return incident

    async def similar(
        self, incident: Incident, evidence: tuple[Evidence, ...] = (), *, limit: int = 5
    ) -> tuple[SimilarIncident, ...]:
        text = " ".join(
            (
                incident.title,
                incident.summary,
                incident.affected_service or "",
                *(item.observation for item in evidence if item.origin is EvidenceOrigin.CURRENT),
            )
        )
        return await self._repository.search(embed(text), limit=limit)

    async def evidence_bundle(
        self,
        incident: Incident,
        investigation_id: UUID,
        evidence: tuple[Evidence, ...],
    ) -> EvidenceBundle:
        from datetime import UTC, datetime

        started = datetime.now(UTC)
        matches = await self.similar(incident, evidence)
        priors = tuple(
            Evidence(
                source=EvidenceSource.MEMORY,
                origin=EvidenceOrigin.HISTORICAL_PRIOR,
                service=match.incident.root_cause_service,
                signal="similar_incident",
                observation=(
                    f"Historical incident '{match.incident.title}' had root cause "
                    f"{match.incident.root_cause_service} / {match.incident.failure_mode}. "
                    "This is a candidate prior, not current-incident evidence."
                ),
                supports=(f"service:{match.incident.root_cause_service}",),
                query_reference=f"memory://historical/{match.incident.id}",
                confidence=max(0.0, match.similarity),
                attributes={
                    "similarity": max(0.0, match.similarity),
                    "historical_incident_id": str(match.incident.id),
                    "resolution": match.incident.resolution,
                },
            )
            for match in matches
            if match.similarity > 0
        )
        completed = datetime.now(UTC)
        audit = ToolCallAudit(
            incident_id=incident.id,
            investigation_id=investigation_id,
            agent_id=AgentRole.MEMORY,
            tool_name="retrieve_similar_incidents",
            arguments={"limit": 5, "embedding_dimensions": _DIMENSIONS},
            started_at=started,
            completed_at=completed,
            status="success",
            result_bytes=sum(len(item.model_dump_json()) for item in priors),
            evidence_ids=tuple(item.id for item in priors),
        )
        return EvidenceBundle(agent=AgentRole.MEMORY, evidence=priors, tool_calls=(audit,))


def embed(text: str) -> tuple[float, ...]:
    """Stable feature-hash embedding suitable for offline/reproducible evaluation."""

    vector = [0.0] * _DIMENSIONS
    for token in _TOKEN.findall(text.lower()):
        digest = hashlib.sha256(token.encode()).digest()
        index = int.from_bytes(digest[:4], "big") % _DIMENSIONS
        sign = 1.0 if digest[4] & 1 else -1.0
        vector[index] += sign
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return tuple(vector)
    return tuple(value / norm for value in vector)


def cosine(left: Iterable[float], right: Iterable[float]) -> float:
    """Reference cosine implementation used by tests and offline evaluation."""

    left_tuple, right_tuple = tuple(left), tuple(right)
    if len(left_tuple) != len(right_tuple):
        raise ValueError("vectors must have equal dimensions")
    similarity = sum(a * b for a, b in zip(left_tuple, right_tuple, strict=True))
    return max(-1.0, min(1.0, similarity))


def _vector_literal(values: tuple[float, ...]) -> str:
    if len(values) != _DIMENSIONS or not all(math.isfinite(value) for value in values):
        raise ValueError(f"embedding must contain {_DIMENSIONS} finite dimensions")
    return "[" + ",".join(f"{value:.10f}" for value in values) + "]"


def _historical_text(incident: HistoricalIncident) -> str:
    return " ".join(
        (
            incident.title,
            incident.summary,
            incident.root_cause_service,
            incident.failure_mode,
            *incident.services,
            *incident.symptoms,
        )
    )

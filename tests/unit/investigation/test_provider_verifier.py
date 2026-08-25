"""Hypothesis grounding and verification tests."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx

from rootlens.investigation.contracts import (
    AgentRole,
    Evidence,
    EvidenceOrigin,
    EvidenceSource,
    Hypothesis,
    HypothesisStatus,
    Incident,
)
from rootlens.investigation.provider import (
    DeterministicHypothesisProvider,
    OpenAIResponsesProvider,
)
from rootlens.investigation.verifier import EvidenceVerifier
from rootlens.telemetry import QueryWindow


async def test_deterministic_provider_only_cites_current_evidence() -> None:
    incident = _incident()
    current = _evidence(EvidenceOrigin.CURRENT, 0.9)
    historical = _evidence(EvidenceOrigin.HISTORICAL_PRIOR, 1.0)

    result = await DeterministicHypothesisProvider().synthesize(
        incident, (historical, current), generated_by=AgentRole.SINGLE
    )

    assert result.hypotheses[0].evidence_for == (current.id,)
    assert historical.id not in result.hypotheses[0].evidence_for


def test_verifier_rejects_unsupported_and_removes_unknown_references() -> None:
    evidence = _evidence(EvidenceOrigin.CURRENT, 0.8)
    unsupported = Hypothesis(
        id="service:checkout",
        rank=1,
        root_cause_service="checkout",
        component="checkout",
        failure_mode="latency regression",
        description="candidate",
        evidence_for=(uuid4(),),
        confidence=0.9,
        status=HypothesisStatus.SUPPORTED,
        generated_by=AgentRole.MANAGER,
    )

    result = EvidenceVerifier().verify((unsupported,), (evidence,))

    assert result[0].status is HypothesisStatus.REJECTED
    assert result[0].evidence_for == ()
    assert result[0].confidence == 0.1


async def test_openai_provider_uses_strict_schema_and_validates_evidence_ids() -> None:
    evidence = _evidence(EvidenceOrigin.CURRENT, 0.8)

    def respond(request: httpx.Request) -> httpx.Response:
        payload = __import__("json").loads(request.content)
        schema = payload["text"]["format"]
        assert payload["store"] is False
        assert schema["strict"] is True
        assert schema["schema"]["additionalProperties"] is False
        output = {
            "hypotheses": [
                {
                    "id": "service:checkout",
                    "root_cause_service": "checkout",
                    "component": "checkout",
                    "failure_mode": "request failures",
                    "description": "Grounded candidate",
                    "predicted_observations": [],
                    "evidence_for": [str(evidence.id), str(uuid4())],
                    "evidence_against": [],
                    "confidence": 0.8,
                    "status": "supported",
                }
            ]
        }
        return httpx.Response(
            200,
            json={
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {"type": "output_text", "text": __import__("json").dumps(output)}
                        ],
                    }
                ],
                "usage": {"input_tokens": 10, "output_tokens": 5},
            },
        )

    provider = OpenAIResponsesProvider(
        api_key="test", model="test-model", transport=httpx.MockTransport(respond)
    )
    result = await provider.synthesize(_incident(), (evidence,), generated_by=AgentRole.MANAGER)

    assert result.hypotheses[0].evidence_for == (evidence.id,)
    assert result.usage.llm_calls == 1
    assert result.usage.input_tokens == 10


def _incident() -> Incident:
    start = datetime(2026, 8, 25, 12, tzinfo=UTC)
    return Incident(
        title="Checkout errors",
        affected_service="frontend",
        window=QueryWindow(start=start, end=start + timedelta(minutes=5)),
    )


def _evidence(origin: EvidenceOrigin, confidence: float) -> Evidence:
    return Evidence(
        source=(
            EvidenceSource.MEMORY
            if origin is EvidenceOrigin.HISTORICAL_PRIOR
            else EvidenceSource.METRICS
        ),
        origin=origin,
        service="checkout",
        signal="error_rate",
        observation="Elevated failures",
        query_reference="telemetry://prometheus/test",
        confidence=confidence,
        attributes={"anomaly_score": confidence},
    )

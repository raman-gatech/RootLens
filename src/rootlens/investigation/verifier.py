"""Adversarial evidence verifier for final hypothesis claims."""

from __future__ import annotations

from rootlens.investigation.contracts import (
    Evidence,
    EvidenceOrigin,
    Hypothesis,
    HypothesisStatus,
)


class EvidenceVerifier:
    def verify(
        self, hypotheses: tuple[Hypothesis, ...], evidence: tuple[Evidence, ...]
    ) -> tuple[Hypothesis, ...]:
        available = {item.id: item for item in evidence}
        verified: list[Hypothesis] = []
        for hypothesis in hypotheses:
            supporting = tuple(
                item
                for item in hypothesis.evidence_for
                if item in available and available[item].origin is EvidenceOrigin.CURRENT
            )
            opposing = tuple(item for item in hypothesis.evidence_against if item in available)
            status = hypothesis.status
            confidence = hypothesis.confidence
            if not supporting:
                status = HypothesisStatus.REJECTED
                confidence = min(confidence, 0.1)
            elif opposing:
                support_strength = max(available[item].confidence for item in supporting)
                oppose_strength = max(available[item].confidence for item in opposing)
                if oppose_strength >= support_strength:
                    status = HypothesisStatus.WEAK
                    confidence = min(confidence, support_strength * 0.5)
            verified.append(
                hypothesis.model_copy(
                    update={
                        "evidence_for": supporting,
                        "evidence_against": opposing,
                        "status": status,
                        "confidence": round(confidence, 6),
                    }
                )
            )
        verified.sort(key=lambda item: (-item.confidence, item.rank, item.id))
        return tuple(
            item.model_copy(update={"rank": rank}) for rank, item in enumerate(verified, start=1)
        )

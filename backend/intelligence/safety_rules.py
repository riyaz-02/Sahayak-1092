"""Deterministic handover and safety rules.

The LLM can analyze the utterance, but this module decides whether autonomy is
allowed. Keeping these rules deterministic makes the system easier to audit.
"""

from __future__ import annotations

from collections.abc import Iterable

from backend.config import Settings, get_settings
from backend.intelligence.schemas import CallAnalysis, HandoverDecision, HandoverReason


DISTRESS_SENTIMENTS = {"distressed", "angry"}


def evaluate_handover(
    analysis: CallAnalysis,
    current_attempt_count: int,
    settings: Settings | None = None,
    distress_sentiments: Iterable[str] = DISTRESS_SENTIMENTS,
) -> HandoverDecision:
    """Return the deterministic handover decision for an analyzed utterance."""

    cfg = settings or get_settings()
    distress = {item.lower() for item in distress_sentiments}
    sentiment = (analysis.sentiment or "").lower()

    if analysis.caller_wants_human:
        return HandoverDecision(
            needs_handover=True,
            reason=HandoverReason.CALLER_REQUESTED,
            explanation="Caller explicitly requested a human officer.",
        )

    if analysis.urgency >= cfg.extreme_urgency_threshold or (
        sentiment in distress and analysis.urgency >= cfg.autonomous_confidence_threshold
    ):
        return HandoverDecision(
            needs_handover=True,
            reason=HandoverReason.HIGH_URGENCY,
            explanation="Extreme urgency or distress was detected.",
        )

    if analysis.confidence < cfg.low_confidence_threshold:
        next_attempt = current_attempt_count + 1
        if next_attempt >= cfg.low_confidence_max_attempts:
            return HandoverDecision(
                needs_handover=True,
                reason=HandoverReason.LOW_CONFIDENCE,
                attempt_increment=1,
                explanation="Understanding confidence stayed low after retry limit.",
            )
        return HandoverDecision(
            needs_handover=False,
            attempt_increment=1,
            explanation="Low confidence detected; caller should be asked to repeat.",
        )

    return HandoverDecision(
        needs_handover=False,
        explanation="No deterministic handover condition matched.",
    )

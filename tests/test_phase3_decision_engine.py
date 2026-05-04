from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.config import Settings
from backend.intelligence.analyzer import DeterministicAnalyzer
from backend.intelligence.safety_rules import evaluate_handover
from backend.intelligence.schemas import (
    CallAnalysis,
    CallPhase,
    CallState,
    HandoverReason,
)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("text", "expected_language", "expected_category"),
    [
        ("My phone was stolen at Majestic bus stand", "english", "theft"),
        ("मेरा मोबाइल चोरी हो गया है", "hindi", "theft"),
        ("ನನ್ನ ಮೊಬೈಲ್ ಕಳವು ಆಗಿದೆ", "kannada", "theft"),
    ],
)
async def test_deterministic_analyzer_returns_structured_multilingual_analysis(
    text: str,
    expected_language: str,
    expected_category: str,
) -> None:
    analyzer = DeterministicAnalyzer()

    analysis = await analyzer.analyze(text, CallState(call_sid="phase3-language"))

    assert analysis.language == expected_language
    assert analysis.category == expected_category
    assert analysis.confidence >= 0.8
    assert analysis.summary
    assert 0.0 <= analysis.urgency <= 1.0


def test_call_analysis_schema_rejects_invalid_shape() -> None:
    with pytest.raises(ValidationError):
        CallAnalysis(urgency=1.5)

    with pytest.raises(ValidationError):
        CallAnalysis(extra_field="not allowed")


def test_handover_rules_cover_required_exception_paths() -> None:
    settings = Settings(
        low_confidence_threshold=0.5,
        low_confidence_max_attempts=2,
        autonomous_confidence_threshold=0.7,
        extreme_urgency_threshold=0.9,
    )

    human = evaluate_handover(
        CallAnalysis(caller_wants_human=True, confidence=0.95),
        current_attempt_count=0,
        settings=settings,
    )
    assert human.needs_handover is True
    assert human.reason == HandoverReason.CALLER_REQUESTED

    urgent = evaluate_handover(
        CallAnalysis(urgency=0.95, sentiment="calm", confidence=0.95),
        current_attempt_count=0,
        settings=settings,
    )
    assert urgent.needs_handover is True
    assert urgent.reason == HandoverReason.HIGH_URGENCY

    first_low_confidence = evaluate_handover(
        CallAnalysis(confidence=0.2, urgency=0.2),
        current_attempt_count=0,
        settings=settings,
    )
    assert first_low_confidence.needs_handover is False
    assert first_low_confidence.attempt_increment == 1

    second_low_confidence = evaluate_handover(
        CallAnalysis(confidence=0.2, urgency=0.2),
        current_attempt_count=1,
        settings=settings,
    )
    assert second_low_confidence.needs_handover is True
    assert second_low_confidence.reason == HandoverReason.LOW_CONFIDENCE


@pytest.mark.asyncio
async def test_normal_confident_issue_enters_vachan_before_final_action(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from backend import decision_engine

    decision_engine.call_repository.reset_for_tests()
    decision_engine.active_calls.clear()
    monkeypatch.setattr(
        decision_engine,
        "settings",
        Settings(openai_api_key="", analysis_provider="deterministic"),
    )

    async def fake_response(
        call_state: CallState,
        analysis: CallAnalysis,
        resolution: str | None = None,
    ) -> str:
        if call_state.current_phase == CallPhase.VACHAN_PENDING.value:
            return "I understood your phone was stolen. Is this correct?"
        return "I am listening."

    async def fake_resolution(analysis: CallAnalysis, call_state: CallState) -> str:
        return "Register the phone theft complaint and advise SIM blocking."

    async def fake_similar(analysis: CallAnalysis, call_state: CallState) -> None:
        return None

    monkeypatch.setattr(decision_engine, "generate_response", fake_response)
    monkeypatch.setattr(decision_engine, "_generate_resolution", fake_resolution)
    monkeypatch.setattr(decision_engine, "find_similar_case", fake_similar)

    result = await decision_engine.process_caller_input(
        call_sid="phase3-vachan",
        text="My phone was stolen at the bus stand",
        caller_number="+919000000001",
    )

    assert result["action"] == "continue"
    assert result["call_state"]["current_phase"] == CallPhase.VACHAN_PENDING.value
    assert result["call_state"]["outcome"] is None
    assert result["analysis"]["category"] == "theft"

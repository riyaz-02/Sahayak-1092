from __future__ import annotations

import pytest

from backend.config import Settings
from backend.intelligence.schemas import CallAnalysis, CallPhase, CallState


async def _install_phase5_fakes(monkeypatch: pytest.MonkeyPatch):
    from backend import decision_engine

    decision_engine.call_repository.reset_for_tests()
    decision_engine.active_calls.clear()
    monkeypatch.setattr(
        decision_engine,
        "settings",
        Settings(
            openai_api_key="",
            analysis_provider="deterministic",
            embedding_provider="deterministic",
        ),
    )

    async def fake_response(
        call_state: CallState,
        analysis: CallAnalysis,
        resolution: str | None = None,
    ) -> str:
        phase = call_state.current_phase
        if phase == CallPhase.VACHAN_PENDING.value:
            return "I understood the issue. Is this correct? Please say yes, no, or tell me what is wrong."
        if phase == CallPhase.VACHAN_PARTIAL.value:
            fields = ", ".join(call_state.pending_clarification_fields or ["description"])
            return f"Please confirm only the correct {fields}."
        if phase == CallPhase.CLARIFYING.value:
            return "Please tell me what was wrong in my understanding."
        if phase == CallPhase.RESOLVED.value:
            return "Confirmed. Your complaint has been registered."
        return "I am listening."

    async def fake_resolution(analysis: CallAnalysis, call_state: CallState) -> str:
        return "Register the phone theft complaint and advise SIM blocking."

    async def fake_similar(analysis: CallAnalysis, call_state: CallState) -> None:
        return None

    monkeypatch.setattr(decision_engine, "generate_response", fake_response)
    monkeypatch.setattr(decision_engine, "_generate_resolution", fake_resolution)
    monkeypatch.setattr(decision_engine, "find_similar_case", fake_similar)
    return decision_engine


@pytest.mark.asyncio
async def test_vachan_pending_does_not_register_before_confirmation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    decision_engine = await _install_phase5_fakes(monkeypatch)

    result = await decision_engine.process_caller_input(
        call_sid="phase5-no-early-registration",
        text="My phone was stolen at the bus stand",
        caller_number="+919333333333",
    )
    events = decision_engine.call_repository.fetch_call_events(
        "phase5-no-early-registration",
        limit=20,
    )
    event_types = {event["event_type"] for event in events}

    assert result["call_state"]["current_phase"] == CallPhase.VACHAN_PENDING.value
    assert result["call_state"]["complaint_registered"] is False
    assert "vachan_requested" in event_types
    assert "complaint_registered" not in event_types


@pytest.mark.asyncio
async def test_yes_confirmation_resolves_and_registers_action(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    decision_engine = await _install_phase5_fakes(monkeypatch)

    await decision_engine.process_caller_input(
        call_sid="phase5-yes",
        text="My phone was stolen at the bus stand",
        caller_number="+919333333334",
    )
    result = await decision_engine.process_caller_input(
        call_sid="phase5-yes",
        text="yes",
        caller_number="+919333333334",
    )
    events = decision_engine.call_repository.fetch_call_events("phase5-yes", limit=30)
    event_types = {event["event_type"] for event in events}

    assert result["action"] == "resolve"
    assert result["call_state"]["current_phase"] == CallPhase.RESOLVED.value
    assert result["call_state"]["complaint_registered"] is True
    assert "vachan_confirmed" in event_types
    assert "complaint_registered" in event_types


@pytest.mark.asyncio
async def test_no_confirmation_returns_to_clarifying_flow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    decision_engine = await _install_phase5_fakes(monkeypatch)

    await decision_engine.process_caller_input(
        call_sid="phase5-no",
        text="My phone was stolen at the bus stand",
        caller_number="+919333333335",
    )
    result = await decision_engine.process_caller_input(
        call_sid="phase5-no",
        text="no",
        caller_number="+919333333335",
    )
    events = decision_engine.call_repository.fetch_call_events("phase5-no", limit=30)
    event_types = {event["event_type"] for event in events}

    assert result["action"] == "continue"
    assert result["call_state"]["current_phase"] == CallPhase.CLARIFYING.value
    assert result["call_state"]["complaint_registered"] is False
    assert "vachan_rejected" in event_types
    assert "vachan_correction_requested" in event_types


@pytest.mark.asyncio
async def test_partial_confirmation_asks_targeted_follow_up_then_rechecks_vachan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    decision_engine = await _install_phase5_fakes(monkeypatch)

    await decision_engine.process_caller_input(
        call_sid="phase5-partial",
        text="My phone was stolen at Majestic bus stand",
        caller_number="+919333333336",
    )
    partial = await decision_engine.process_caller_input(
        call_sid="phase5-partial",
        text="yes but the location is railway station",
        caller_number="+919333333336",
    )
    corrected = await decision_engine.process_caller_input(
        call_sid="phase5-partial",
        text="platform number 2",
        caller_number="+919333333336",
    )
    events = decision_engine.call_repository.fetch_call_events("phase5-partial", limit=40)
    event_types = {event["event_type"] for event in events}

    assert partial["call_state"]["current_phase"] == CallPhase.VACHAN_PARTIAL.value
    assert partial["call_state"]["pending_clarification_fields"] == ["location"]
    assert partial["call_state"]["complaint_registered"] is False
    assert corrected["call_state"]["current_phase"] == CallPhase.VACHAN_PENDING.value
    assert "platform number 2" in corrected["call_state"]["ai_summary"]
    assert "vachan_partial" in event_types
    assert "vachan_correction_requested" in event_types

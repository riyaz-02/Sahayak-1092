from __future__ import annotations

import pytest

from backend.config import Settings
from backend.intelligence.schemas import CallAnalysis, CallState
from backend.persistence.repository import CallStateRepository


def test_repository_uses_local_fallback_without_supabase_or_redis() -> None:
    repo = CallStateRepository(Settings(supabase_url="", supabase_key="", redis_url=""))
    state = CallState(call_sid="phase2-local-1", caller_number="+919999999999")

    record = repo.create_call_state(state)
    state.transcript.append({"role": "caller", "text": "My phone was stolen"})
    state.ai_summary = "Phone theft"
    analysis = CallAnalysis(category="theft", summary="Phone theft", confidence=0.91)
    updated = repo.update_call_state(state, analysis=analysis)
    event = repo.append_call_event(
        call_sid=state.call_sid,
        event_type="analysis_completed",
        payload=analysis.as_event_payload(),
        call_state=state,
        analysis=analysis,
    )

    assert record["call_sid"] == "phase2-local-1"
    assert updated["ai_summary"] == "Phone theft"
    assert repo.fetch_active_calls()[0]["call_sid"] == "phase2-local-1"
    assert repo.fetch_call_transcript("phase2-local-1")[0]["text"] == "My phone was stolen"
    assert event["event_type"] == "analysis_completed"
    assert repo.fetch_call_events("phase2-local-1")[0]["event_type"] == "analysis_completed"


@pytest.mark.asyncio
async def test_text_pipeline_creates_call_record_and_audit_events(monkeypatch: pytest.MonkeyPatch) -> None:
    from backend import decision_engine

    decision_engine.call_repository.reset_for_tests()
    decision_engine.active_calls.clear()

    async def fake_analyse(text: str, call_state: CallState) -> CallAnalysis:
        analysis = CallAnalysis(
            language="english",
            sentiment="calm",
            urgency=0.4,
            confidence=0.95,
            category="theft",
            summary="Phone stolen at bus stand",
            raw_text=text,
        )
        call_state.language = analysis.language
        call_state.analyses.append(analysis.as_event_payload())
        return analysis

    async def fake_response(
        call_state: CallState,
        analysis: CallAnalysis,
        resolution: str | None = None,
    ) -> str:
        return "I understand your phone was stolen. Is this correct? Please say yes or no."

    async def fake_resolution(analysis: CallAnalysis, call_state: CallState) -> str:
        return "Register a phone theft complaint and advise SIM blocking."

    async def fake_similar(analysis: CallAnalysis, call_state: CallState) -> None:
        return None

    monkeypatch.setattr(decision_engine, "analyse_utterance", fake_analyse)
    monkeypatch.setattr(decision_engine, "generate_response", fake_response)
    monkeypatch.setattr(decision_engine, "_generate_resolution", fake_resolution)
    monkeypatch.setattr(decision_engine, "find_similar_case", fake_similar)

    result = await decision_engine.process_caller_input(
        call_sid="phase2-pipeline-1",
        text="My phone was stolen at Majestic bus stand",
        caller_number="+919888888888",
    )
    result = await decision_engine.process_caller_input(
        call_sid="phase2-pipeline-1",
        text="It was stolen while boarding the bus",
        caller_number="+919888888888",
    )

    calls = decision_engine.call_repository.fetch_recent_calls()
    events = decision_engine.call_repository.fetch_call_events("phase2-pipeline-1", limit=20)
    event_types = {event["event_type"] for event in events}

    assert result["action"] == "continue"
    assert calls[0]["call_sid"] == "phase2-pipeline-1"
    assert "call_started" in event_types
    assert "utterance_received" in event_types
    assert "analysis_completed" in event_types
    assert "vachan_requested" in event_types

from __future__ import annotations

import pytest

from backend.config import Settings
from backend.intelligence.schemas import CallAnalysis, CallPhase, CallState
from backend.persistence.complaints import ComplaintRegistry


def test_complaint_registry_creates_structured_local_record() -> None:
    registry = ComplaintRegistry(Settings(supabase_url="", supabase_key=""))
    call_state = CallState(
        call_sid="phase8-complaint-ABC123",
        caller_number="+919444444444",
        language="english",
    )
    call_state.ai_summary = "Caller reports mobile phone theft at Majestic bus stand."
    call_state.transcript.append(
        {
            "role": "caller",
            "text": "My phone was stolen at Majestic bus stand while boarding the bus.",
        }
    )
    analysis = CallAnalysis(
        language="english",
        category="theft",
        urgency=0.62,
        confidence=0.9,
        summary=call_state.ai_summary,
        raw_text=call_state.transcript[0]["text"],
    )

    complaint = registry.register_ai_resolved_complaint(
        call_state=call_state,
        analysis=analysis,
        category="theft",
        resolution="Register phone theft complaint and advise SIM blocking.",
    )
    timeline = registry.get_timeline(complaint["reference_id"])

    assert complaint["reference_id"].startswith("SAH-THE-")
    assert complaint["call_sid"] == "phase8-complaint-ABC123"
    assert complaint["category"] == "theft"
    assert complaint["location"] == "Majestic bus stand"
    assert complaint["transcript_ref"] == "call_logs.call_sid:phase8-complaint-ABC123:transcript"
    assert complaint["government_payload"]["action"] == "register_complaint"
    assert complaint["government_payload"]["priority"] == "medium"
    assert {event["event_type"] for event in timeline} == {
        "complaint_registered",
        "government_payload_created",
    }


@pytest.mark.asyncio
async def test_confirmed_ai_resolution_creates_complaint_reference_and_timeline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from backend import decision_engine

    registry = ComplaintRegistry(Settings(supabase_url="", supabase_key=""))
    decision_engine.call_repository.reset_for_tests()
    decision_engine.active_calls.clear()
    monkeypatch.setattr(decision_engine, "complaint_registry", registry)
    monkeypatch.setattr(
        decision_engine,
        "settings",
        Settings(
            openai_api_key="",
            analysis_provider="deterministic",
            embedding_provider="deterministic",
        ),
    )

    async def fake_analyse(text: str, call_state: CallState) -> CallAnalysis:
        if "yes" in text.lower():
            analysis = CallAnalysis(
                language="english",
                category="theft",
                urgency=0.62,
                confidence=0.95,
                is_confirmation=True,
                confirmation_status="yes",
                summary=call_state.ai_summary,
                raw_text=text,
            )
        else:
            analysis = CallAnalysis(
                language="english",
                category="theft",
                urgency=0.62,
                confidence=0.95,
                summary="Caller reports mobile phone theft at Majestic bus stand.",
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
        if call_state.current_phase == CallPhase.RESOLVED.value:
            return f"Confirmed. Complaint reference {call_state.complaint_reference_id}."
        return "I understood the issue. Is this correct?"

    async def fake_resolution(analysis: CallAnalysis, call_state: CallState) -> str:
        return "Register phone theft complaint and advise SIM blocking."

    async def fake_similar(analysis: CallAnalysis, call_state: CallState) -> None:
        return None

    monkeypatch.setattr(decision_engine, "analyse_utterance", fake_analyse)
    monkeypatch.setattr(decision_engine, "generate_response", fake_response)
    monkeypatch.setattr(decision_engine, "_generate_resolution", fake_resolution)
    monkeypatch.setattr(decision_engine, "find_similar_case", fake_similar)

    await decision_engine.process_caller_input(
        call_sid="phase8-pipeline",
        text="My phone was stolen at Majestic bus stand",
        caller_number="+919555555555",
    )
    result = await decision_engine.process_caller_input(
        call_sid="phase8-pipeline",
        text="yes",
        caller_number="+919555555555",
    )
    complaints = registry.list_complaints()
    reference_id = result["call_state"]["complaint_reference_id"]
    timeline = registry.get_timeline(reference_id)
    events = decision_engine.call_repository.fetch_call_events("phase8-pipeline", limit=50)

    assert result["action"] == "resolve"
    assert result["call_state"]["complaint_registered"] is True
    assert reference_id.startswith("SAH-THE-")
    assert complaints[0]["reference_id"] == reference_id
    assert complaints[0]["status"] == "registered"
    assert len(timeline) == 2
    assert "complaint_timeline_updated" in {event["event_type"] for event in events}

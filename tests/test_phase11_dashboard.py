from __future__ import annotations

import json

import pytest

from backend.config import Settings
from backend.intelligence.schemas import CallAnalysis, CallState
from backend.persistence.repository import CallStateRepository


class FakeJsonRequest:
    def __init__(self, body: dict):
        self.body = body

    async def json(self) -> dict:
        return self.body


@pytest.mark.asyncio
async def test_dashboard_correction_endpoint_updates_state_and_audit_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from backend import main

    repo = CallStateRepository(Settings(supabase_url="", supabase_key="", redis_url=""))
    monkeypatch.setattr(main, "call_repository", repo)

    state = CallState(call_sid="phase11-correct", caller_number="+919100000011")
    analysis = CallAnalysis(
        language="english",
        category="theft",
        urgency=0.42,
        confidence=0.82,
        summary="Caller reports a phone theft.",
    )
    state.language = "english"
    state.ai_summary = analysis.summary
    state.analyses.append(analysis.as_event_payload())
    repo.create_call_state(state)
    repo.update_call_state(state, analysis=analysis)

    response = await main.api_apply_call_corrections(
        "phase11-correct",
        FakeJsonRequest(
            {
                "category": "cyber",
                "urgency": 0.77,
                "summary": "Caller reports UPI fraud after phone theft.",
                "resolution": "Register cyber complaint and block UPI access.",
                "notes": "Officer corrected category.",
            }
        ),
    )
    payload = json.loads(response.body)
    events = repo.fetch_call_events("phase11-correct", limit=20)

    assert payload["status"] == "ok"
    assert payload["call_state"]["ai_summary"] == "Caller reports UPI fraud after phone theft."
    assert payload["call_state"]["resolution"] == "Register cyber complaint and block UPI access."
    assert payload["call_state"]["analyses"][-1]["category"] == "cyber"
    assert payload["call_state"]["analyses"][-1]["urgency"] == 0.77
    assert "ai_correction_applied" in {event["event_type"] for event in events}


@pytest.mark.asyncio
async def test_dashboard_can_add_corrected_resolution_to_local_knowledge_base(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from backend import main

    repo = CallStateRepository(Settings(supabase_url="", supabase_key="", redis_url=""))
    monkeypatch.setattr(main, "call_repository", repo)
    monkeypatch.setattr(main, "settings", Settings(supabase_url="", supabase_key=""))
    monkeypatch.setattr(main.db, "get_all_resolved_cases", lambda limit=100: [])
    main.local_learned_cases.clear()

    state = CallState(call_sid="phase11-learn", caller_number="+919100000012")
    analysis = CallAnalysis(
        language="english",
        category="theft",
        urgency=0.66,
        confidence=0.9,
        summary="Caller reports stolen phone at bus stand.",
    )
    state.language = "english"
    state.ai_summary = analysis.summary
    state.resolution = "Register phone theft complaint and advise SIM blocking."
    state.analyses.append(analysis.as_event_payload())
    repo.create_call_state(state)
    repo.update_call_state(state, analysis=analysis)

    response = await main.api_add_resolved_case_from_call(
        FakeJsonRequest({"call_sid": "phase11-learn", "tags": ["theft", "phone"]})
    )
    payload = json.loads(response.body)
    cases_response = await main.api_resolved_cases()
    cases_payload = json.loads(cases_response.body)
    events = repo.fetch_call_events("phase11-learn", limit=20)

    assert payload["status"] == "ok"
    assert payload["source"] == "local_fallback"
    assert payload["case"]["source_call_sid"] == "phase11-learn"
    assert len(main.local_learned_cases) == 1
    assert cases_payload["cases"][0]["source_call_sid"] == "phase11-learn"
    assert "knowledge_base_case_added" in {event["event_type"] for event in events}

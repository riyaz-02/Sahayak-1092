from __future__ import annotations

import pytest

from backend.config import Settings
from backend.intelligence.schemas import CallAnalysis, CallPhase, CallState
from backend.routing.officer_router import score_agent_with_breakdown, select_best_agent
from backend.routing.transfer_service import TransferRequest, WarmTransferService


def test_routing_score_returns_auditable_breakdown() -> None:
    agent = {
        "id": "agent-1",
        "name": "Inspector Ravi",
        "languages": ["kannada", "english"],
        "dialects": ["bengaluru"],
        "specialties": ["theft"],
        "avg_wait_sec": 12,
        "current_load": 1,
    }

    breakdown = score_agent_with_breakdown(
        agent=agent,
        call_language="kannada",
        dialect="bengaluru",
        category="theft",
        urgency=0.82,
    )

    assert breakdown["score"] > 0.9
    assert breakdown["weights"]["urgency_specialty"] == 0.5
    assert breakdown["weights"]["language_dialect"] == 0.4
    assert breakdown["raw"]["language_dialect_fit"] == 1.0
    assert breakdown["raw"]["specialty_fit"] == 1.0
    assert breakdown["weighted"]["load_penalty"] == 0.0


def test_select_best_agent_includes_ranked_agents() -> None:
    agents = [
        {
            "id": "agent-slow",
            "name": "Slow Officer",
            "languages": ["english"],
            "specialties": ["general"],
            "avg_wait_sec": 100,
            "current_load": 0,
        },
        {
            "id": "agent-best",
            "name": "Best Officer",
            "languages": ["hindi", "english"],
            "specialties": ["domestic"],
            "avg_wait_sec": 10,
            "current_load": 0,
        },
    ]

    selected = select_best_agent(
        agents=agents,
        call_language="hindi",
        category="domestic",
        urgency=0.95,
    )

    assert selected is not None
    assert selected["agent"]["id"] == "agent-best"
    assert selected["score_breakdown"]["score"] == selected["score"]
    assert selected["ranked_agents"][0]["agent_id"] == "agent-best"


@pytest.mark.asyncio
async def test_handover_decision_returns_context_and_score_breakdown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from backend import decision_engine

    decision_engine.call_repository.reset_for_tests()
    decision_engine.active_calls.clear()
    monkeypatch.setattr(
        decision_engine,
        "settings",
        Settings(openai_api_key="", analysis_provider="deterministic", transfer_mode="mock"),
    )

    agents = [
        {
            "id": "agent-phase9",
            "name": "Inspector Meera",
            "phone": "+919999999999",
            "languages": ["english", "hindi"],
            "dialects": [],
            "specialties": ["theft"],
            "avg_wait_sec": 8,
            "current_load": 0,
        }
    ]
    monkeypatch.setattr(decision_engine.db, "get_available_agents", lambda language=None: agents)

    async def fake_analyse(text: str, call_state: CallState) -> CallAnalysis:
        analysis = CallAnalysis(
            language="english",
            category="theft",
            urgency=0.6,
            confidence=0.95,
            caller_wants_human=True,
            summary="Caller wants a human officer for a phone theft report.",
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
        return "I am connecting you to an officer now."

    monkeypatch.setattr(decision_engine, "analyse_utterance", fake_analyse)
    monkeypatch.setattr(decision_engine, "generate_response", fake_response)

    result = await decision_engine.process_caller_input(
        call_sid="phase9-handover",
        text="I want to talk to an officer",
        caller_number="+919111111111",
    )

    context = result["handover_context"]
    assert result["action"] == "handover"
    assert result["agent"]["id"] == "agent-phase9"
    assert context["selected_agent"]["id"] == "agent-phase9"
    assert context["routing_score_breakdown"]["score"] == result["call_state"]["routing_score_breakdown"]["score"]
    assert context["officer_first_sentence"]
    assert result["call_state"]["transfer_status"] == "awaiting_officer_acceptance"


class FakeJsonRequest:
    def __init__(self, body: dict):
        self.body = body

    async def json(self) -> dict:
        return self.body


@pytest.mark.asyncio
async def test_mock_transfer_acceptance_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    from backend import decision_engine, main

    decision_engine.call_repository.reset_for_tests()
    decision_engine.active_calls.clear()
    monkeypatch.setattr(main, "transfer_service", WarmTransferService(Settings(transfer_mode="mock")))
    monkeypatch.setattr(main.db, "increment_agent_load", lambda agent_id: None)

    state = decision_engine.get_or_create_call("phase9-accept", "+919222222222")
    state.current_phase = CallPhase.HANDOVER_PENDING.value
    state.agent_id = "agent-accept"
    state.handover_context = {
        "call_sid": "phase9-accept",
        "selected_agent": {
            "id": "agent-accept",
            "name": "Inspector Accepted",
            "phone": "+919333333333",
        },
        "routing_score": 0.94,
        "routing_score_breakdown": {"score": 0.94},
        "officer_first_sentence": "Hello, I already have the summary.",
    }
    state.routing_score_breakdown = {"score": 0.94}
    decision_engine.call_repository.update_call_state(state)

    response = await main.api_accept_handover(
        "phase9-accept",
        FakeJsonRequest({"agent_id": "agent-accept", "notes": "Taking over"}),
    )

    assert response.status_code == 200
    import json

    payload = json.loads(response.body)
    assert payload["status"] == "ok"
    assert payload["transfer"]["mode"] == "mock"
    assert payload["transfer"]["status"] == "mock_transfer_ready"
    events = decision_engine.call_repository.fetch_call_events("phase9-accept", limit=10)
    assert "handover_accepted" in {event["event_type"] for event in events}
    assert "transfer_completed" in {event["event_type"] for event in events}


def test_twilio_transfer_reports_not_configured_without_credentials() -> None:
    service = WarmTransferService(
        Settings(
            transfer_mode="twilio",
            twilio_account_sid="",
            twilio_auth_token="",
            twilio_phone_number="",
        )
    )

    result = service.accept_handover(
        TransferRequest(
            call_sid="phase9-twilio",
            agent={"id": "agent-twilio", "phone": "+919999999999"},
            handover_context={},
        )
    )

    assert result.success is False
    assert result.mode == "twilio"
    assert result.status == "not_configured"

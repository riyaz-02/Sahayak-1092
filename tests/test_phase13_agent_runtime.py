from __future__ import annotations

import pytest

from backend.agent import SahayakAgent
from backend.decision_engine import active_calls
from backend.intelligence.schemas import CallPhase, CallState
from backend.persistence.repository import get_call_repository, state_to_dict


@pytest.fixture(autouse=True)
def reset_agent_state():
    active_calls.clear()
    get_call_repository().reset_for_tests()
    yield
    active_calls.clear()
    get_call_repository().reset_for_tests()


def test_agent_tool_registry_exposes_bounded_operational_tools() -> None:
    agent = SahayakAgent()

    tool_names = {tool["name"] for tool in agent.tool_specs()}

    assert "understand_caller" in tool_names
    assert "evaluate_safety_policy" in tool_names
    assert "search_resolved_cases" in tool_names
    assert "request_vachan_confirmation" in tool_names
    assert "register_complaint" in tool_names
    assert "route_to_officer" in tool_names
    assert "enqueue_priority_call" in tool_names


@pytest.mark.asyncio
async def test_agent_runtime_wraps_decision_pipeline_and_records_trace(monkeypatch) -> None:
    async def fake_decision_pipeline(call_sid: str, text: str, caller_number: str = "") -> dict:
        state = CallState(
            call_sid=call_sid,
            caller_number=caller_number,
            language="english",
            current_phase=CallPhase.VACHAN_PENDING.value,
            ai_summary="Caller reports mobile theft.",
            resolution="Register theft complaint and advise caller to block SIM.",
        )
        state.transcript.append({"role": "caller", "text": text})
        get_call_repository().update_call_state(state)
        return {
            "response_text": "I understood your mobile theft report. Is this correct?",
            "action": "continue",
            "analysis": {
                "language": "english",
                "category": "theft",
                "urgency": 0.62,
                "confidence": 0.88,
                "sentiment": "calm",
                "caller_wants_human": False,
            },
            "call_state": state_to_dict(state),
        }

    monkeypatch.setattr("backend.agent.tools.process_caller_input", fake_decision_pipeline)

    agent = SahayakAgent()
    result = await agent.handle_text_turn(
        call_sid="phase13-agent",
        text="My mobile was stolen",
        caller_number="+919100001313",
        language="english",
        channel="api_test",
    )

    assert result["response_text"].startswith("I understood")
    assert result["action"] == "continue"
    assert result["agent_trace"]["agent_type"] == "bounded_emergency_operations_agent"
    assert result["agent_trace"]["final_phase"] == "vachan_pending"
    assert "Vachan confirmation is required before final action." in result["agent_trace"]["safety_notes"]

    tool_names = {tool["name"] for tool in result["agent_trace"]["tool_calls"]}
    assert "load_call_memory" in tool_names
    assert "respond_to_caller" in tool_names
    assert "understand_caller" in tool_names
    assert "evaluate_safety_policy" in tool_names
    assert "request_vachan_confirmation" in tool_names

    event_types = {
        event["event_type"]
        for event in get_call_repository().fetch_call_events(call_sid="phase13-agent", limit=20)
    }
    assert "agent_turn_started" in event_types
    assert "agent_tool_used" in event_types
    assert "agent_turn_completed" in event_types

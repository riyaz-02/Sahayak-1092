from __future__ import annotations

import json

import pytest

from backend.config import Settings
from backend.intelligence.schemas import CallAnalysis, CallOutcome, CallPhase, CallState
from backend.persistence.repository import CallStateRepository
from backend.routing.queue_manager import (
    PriorityQueueManager,
    QUEUE_STATUS_HIGH_HELP_ALERT,
    QUEUE_STATUS_REDIRECTED,
    QUEUE_STATUS_WAITING,
)


def test_priority_queue_orders_by_urgency_and_estimates_wait() -> None:
    manager = PriorityQueueManager(Settings(supabase_url="", supabase_key="", redis_url=""))

    low_state = CallState(call_sid="phase10-low", caller_number="+919100000001")
    high_state = CallState(call_sid="phase10-high", caller_number="+919100000002")
    low = CallAnalysis(
        language="english",
        category="noise",
        urgency=0.35,
        confidence=0.88,
        sentiment="calm",
    )
    high = CallAnalysis(
        language="english",
        category="domestic",
        urgency=0.96,
        confidence=0.93,
        sentiment="distressed",
    )

    manager.enqueue_call(low_state, low, reason="caller_requested_human")
    manager.enqueue_call(high_state, high, reason="extreme_urgency_distress")

    high_entry = manager.get_entry("phase10-high")
    low_entry = manager.get_entry("phase10-low")
    listed = manager.list_entries()

    assert high_entry is not None
    assert low_entry is not None
    assert high_entry.status == QUEUE_STATUS_WAITING
    assert high_entry.position == 1
    assert low_entry.position == 2
    assert low_entry.estimated_wait_sec == 45
    assert listed[0]["call_sid"] == "phase10-high"


def test_demo_mode_uses_shorter_high_help_alert_timeout() -> None:
    demo = PriorityQueueManager(
        Settings(
            demo_mode=True,
            high_help_alert_timeout_sec=120,
            high_help_alert_demo_timeout_sec=7,
            supabase_url="",
            supabase_key="",
        )
    )
    production = PriorityQueueManager(
        Settings(
            demo_mode=False,
            high_help_alert_timeout_sec=120,
            high_help_alert_demo_timeout_sec=7,
            supabase_url="",
            supabase_key="",
        )
    )

    assert demo.queue_timeout_sec() == 7
    assert production.queue_timeout_sec() == 120


@pytest.mark.asyncio
async def test_decision_engine_queues_when_no_agent_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from backend import decision_engine

    repo = CallStateRepository(Settings(supabase_url="", supabase_key="", redis_url=""))
    manager = PriorityQueueManager(
        Settings(
            demo_mode=True,
            high_help_alert_demo_timeout_sec=5,
            supabase_url="",
            supabase_key="",
        )
    )
    decision_engine.active_calls.clear()
    monkeypatch.setattr(decision_engine, "call_repository", repo)
    monkeypatch.setattr(decision_engine, "queue_manager", manager)
    monkeypatch.setattr(
        decision_engine,
        "settings",
        Settings(openai_api_key="", analysis_provider="deterministic", supabase_url="", supabase_key=""),
    )
    monkeypatch.setattr(decision_engine.db, "get_available_agents", lambda language=None: [])

    async def fake_analyse(text: str, call_state: CallState) -> CallAnalysis:
        analysis = CallAnalysis(
            language="english",
            category="theft",
            urgency=0.72,
            confidence=0.95,
            sentiment="anxious",
            caller_wants_human=True,
            summary="Caller wants an officer while all officers are unavailable.",
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
        return "All officers are busy. You are in the priority queue."

    monkeypatch.setattr(decision_engine, "analyse_utterance", fake_analyse)
    monkeypatch.setattr(decision_engine, "generate_response", fake_response)

    result = await decision_engine.process_caller_input(
        call_sid="phase10-queue",
        text="Please connect me to an officer",
        caller_number="+919100000003",
    )

    state = result["call_state"]
    events = repo.fetch_call_events("phase10-queue", limit=20)

    assert result["action"] == "queue"
    assert state["current_phase"] == CallPhase.QUEUED.value
    assert state["outcome"] == CallOutcome.QUEUED.value
    assert state["queue_status"] == QUEUE_STATUS_WAITING
    assert state["queue_position"] == 1
    assert {event["event_type"] for event in events} >= {"queued", "queue_updated"}


@pytest.mark.asyncio
async def test_media_stream_dtmf_and_timeout_update_queue_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from backend import decision_engine, media_stream

    repo = CallStateRepository(Settings(supabase_url="", supabase_key="", redis_url=""))
    manager = PriorityQueueManager(
        Settings(demo_mode=True, high_help_alert_demo_timeout_sec=1, supabase_url="", supabase_key="")
    )
    decision_engine.active_calls.clear()
    monkeypatch.setattr(media_stream, "call_repository", repo)
    monkeypatch.setattr(media_stream, "queue_manager", manager)
    monkeypatch.setattr(media_stream.db, "update_call_log", lambda **fields: fields)

    async def fake_speak(self, text: str, language: str, *, context: str, call_state: CallState):
        return None

    monkeypatch.setattr(media_stream.MediaStreamHandler, "_speak", fake_speak)

    dtmf_state = CallState(
        call_sid="phase10-dtmf",
        caller_number="+919100000004",
        language="english",
        current_phase=CallPhase.QUEUED.value,
    )
    dtmf_analysis = CallAnalysis(language="english", category="medical", urgency=0.8, confidence=0.9)
    manager.apply_to_call_state(dtmf_state, manager.enqueue_call(dtmf_state, dtmf_analysis))
    decision_engine.active_calls[dtmf_state.call_sid] = dtmf_state
    repo.create_call_state(dtmf_state)

    handler = media_stream.MediaStreamHandler(websocket=None)
    handler.call_sid = dtmf_state.call_sid
    await handler._handle_dtmf("2")

    dtmf_entry = manager.get_entry(dtmf_state.call_sid)
    dtmf_events = repo.fetch_call_events(dtmf_state.call_sid, limit=20)
    assert dtmf_entry is not None
    assert dtmf_entry.status == QUEUE_STATUS_REDIRECTED
    assert dtmf_entry.service_target == "ambulance"
    assert dtmf_state.outcome == CallOutcome.HANDED_OVER
    assert "dtmf_redirect" in {event["event_type"] for event in dtmf_events}

    timeout_state = CallState(
        call_sid="phase10-timeout",
        caller_number="+919100000005",
        language="english",
        current_phase=CallPhase.QUEUED.value,
    )
    timeout_analysis = CallAnalysis(language="english", category="general", urgency=0.7, confidence=0.82)
    manager.apply_to_call_state(timeout_state, manager.enqueue_call(timeout_state, timeout_analysis))
    decision_engine.active_calls[timeout_state.call_sid] = timeout_state
    repo.create_call_state(timeout_state)

    handler.call_sid = timeout_state.call_sid
    await handler._queue_timeout(0)

    timeout_entry = manager.get_entry(timeout_state.call_sid)
    timeout_events = repo.fetch_call_events(timeout_state.call_sid, limit=20)
    assert timeout_entry is not None
    assert timeout_entry.status == QUEUE_STATUS_HIGH_HELP_ALERT
    assert timeout_entry.service_target == "police"
    assert timeout_state.outcome == CallOutcome.HANDED_OVER
    assert "high_help_alert" in {event["event_type"] for event in timeout_events}


@pytest.mark.asyncio
async def test_queue_api_returns_entries(monkeypatch: pytest.MonkeyPatch) -> None:
    from backend import main

    manager = PriorityQueueManager(Settings(supabase_url="", supabase_key="", redis_url=""))
    state = CallState(call_sid="phase10-api", caller_number="+919100000006")
    analysis = CallAnalysis(language="english", category="fire", urgency=0.9, confidence=0.91)
    manager.enqueue_call(state, analysis)
    monkeypatch.setattr(main, "queue_manager", manager)

    response = await main.api_queue(include_inactive=False, limit=10)
    payload = json.loads(response.body)

    assert payload["count"] == 1
    assert payload["queue"][0]["call_sid"] == "phase10-api"
    assert payload["queue"][0]["position"] == 1

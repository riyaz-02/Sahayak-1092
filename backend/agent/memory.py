"""Agent memory and trace persistence helpers."""

from __future__ import annotations

from backend.agent.context import AgentTrace
from backend.intelligence.schemas import CallState
from backend.persistence.repository import get_call_repository


class SahayakAgentMemory:
    """Persist agent turn traces through the existing call-event log."""

    def __init__(self):
        self.repository = get_call_repository()

    def record_turn_started(
        self,
        *,
        call_state: CallState,
        channel: str,
        text: str,
    ) -> None:
        self.repository.append_call_event(
            call_sid=call_state.call_sid,
            event_type="agent_turn_started",
            payload={
                "channel": channel,
                "text_length": len(text),
            },
            call_state=call_state,
        )

    def record_tool_call(self, *, call_state: CallState, tool_name: str, payload: dict) -> None:
        self.repository.append_call_event(
            call_sid=call_state.call_sid,
            event_type="agent_tool_used",
            payload={"tool": tool_name, **payload},
            call_state=call_state,
        )

    def record_turn_completed(self, *, call_state: CallState, trace: AgentTrace) -> None:
        self.repository.append_call_event(
            call_sid=call_state.call_sid,
            event_type="agent_turn_completed",
            payload=trace.as_event_payload(),
            call_state=call_state,
        )

"""Main bounded Sahayak agent runtime."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from backend.agent.context import AgentChannel, AgentTurnInput, AgentTurnResult
from backend.agent.memory import SahayakAgentMemory
from backend.agent.policy import SahayakAgentPolicy
from backend.agent.tools import SahayakAgentTools, SahayakToolRegistry
from backend.agent.traces import build_agent_trace
from backend.persistence.repository import get_call_repository


class SahayakAgent:
    """Bounded emergency operations agent.

    This class is the single channel-facing runtime. APIs, dashboard simulators,
    and Twilio voice turns should call this agent instead of reaching directly
    into the decision engine. The agent delegates to the existing decision
    engine so the core workflow remains stable and tested.
    """

    def __init__(
        self,
        *,
        tools: SahayakAgentTools | None = None,
        policy: SahayakAgentPolicy | None = None,
        memory: SahayakAgentMemory | None = None,
    ):
        self.registry = SahayakToolRegistry()
        self.tools = tools or SahayakAgentTools(self.registry)
        self.policy = policy or SahayakAgentPolicy()
        self.memory = memory or SahayakAgentMemory()
        self.repository = get_call_repository()

    def tool_specs(self) -> list[dict[str, Any]]:
        return [tool.model_dump(mode="json") for tool in self.registry.specs()]

    async def handle_text_turn(
        self,
        *,
        call_sid: str,
        text: str,
        caller_number: str = "",
        language: str = "",
        channel: str | AgentChannel = AgentChannel.API_TEST,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        turn_input = AgentTurnInput(
            call_sid=call_sid,
            text=text,
            caller_number=caller_number,
            language=language,
            channel=channel,
            metadata=metadata or {},
        )

        call_state, load_call = self.tools.load_call_memory(
            call_sid=turn_input.call_sid,
            caller_number=turn_input.caller_number,
            language=turn_input.language,
        )
        self.memory.record_turn_started(
            call_state=call_state,
            channel=turn_input.channel.value,
            text=turn_input.text,
        )
        self.memory.record_tool_call(
            call_state=call_state,
            tool_name=load_call.name,
            payload=load_call.model_dump(mode="json"),
        )

        decision, decision_call = await self.tools.run_decision_pipeline(
            call_sid=turn_input.call_sid,
            text=turn_input.text,
            caller_number=turn_input.caller_number,
        )

        updated_state = self.repository.get_call_state(turn_input.call_sid) or call_state
        self.memory.record_tool_call(
            call_state=updated_state,
            tool_name=decision_call.name,
            payload=decision_call.model_dump(mode="json"),
        )

        memory_writes = self._memory_writes(decision)
        trace = build_agent_trace(
            turn_input=turn_input,
            decision=decision,
            tool_calls=[load_call, decision_call],
            safety_notes=self.policy.safety_notes(decision),
            memory_writes=memory_writes,
        )
        self.memory.record_turn_completed(call_state=updated_state, trace=trace)

        return AgentTurnResult(
            decision=decision,
            trace=trace,
            tools=self.registry.specs(),
        ).as_response()

    @staticmethod
    def _memory_writes(decision: dict[str, Any]) -> list[str]:
        call_state = decision.get("call_state") or {}
        writes = ["call_state", "transcript", "call_events"]
        if call_state.get("complaint_reference_id"):
            writes.append("complaints")
            writes.append("complaint_timeline")
        if call_state.get("matched_case_id") or decision.get("similarity"):
            writes.append("similarity_match")
        if call_state.get("queue_entry_id"):
            writes.append("call_queue")
        if call_state.get("handover_context"):
            writes.append("handover_context")
        return writes


@lru_cache(maxsize=1)
def get_sahayak_agent() -> SahayakAgent:
    return SahayakAgent()

"""Tool registry and adapters for the Sahayak bounded agent."""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import Any

from backend.agent.context import AgentToolCall, AgentToolSpec
from backend.decision_engine import get_or_create_call, process_caller_input
from backend.intelligence.schemas import CallState
from backend.persistence.repository import get_call_repository


class SahayakToolRegistry:
    """Registry of tools the Sahayak agent is allowed to use.

    The runtime is intentionally bounded. Tools are explicit, auditable, and
    mapped to existing production modules instead of allowing arbitrary code or
    unrestricted model-chosen actions.
    """

    def __init__(self):
        self._specs = [
            AgentToolSpec(
                name="load_call_memory",
                purpose="Load or create live call state before a turn.",
                reads=["call_state", "redis_optional", "local_memory"],
                writes=["call_state_if_new", "call_started_event_if_new"],
                side_effect=True,
                safety_note="Creates only scoped call memory for the current call SID.",
            ),
            AgentToolSpec(
                name="understand_caller",
                purpose="Analyze language, dialect, sentiment, urgency, intent, category, and confidence.",
                reads=["caller_utterance", "call_state"],
                writes=["analysis_event", "call_state.language", "call_state.dialect"],
                side_effect=True,
                safety_note="Analysis informs policy; it does not directly execute final action.",
            ),
            AgentToolSpec(
                name="evaluate_safety_policy",
                purpose="Apply deterministic handover and autonomy rules.",
                reads=["analysis", "attempt_count", "threshold_settings"],
                writes=["handover_requested_event_when_needed"],
                side_effect=True,
                safety_note="Safety policy gates autonomous action before final resolution.",
            ),
            AgentToolSpec(
                name="search_resolved_cases",
                purpose="Search resolved case memory with local or Supabase pgvector retrieval.",
                reads=["analysis", "resolved_cases", "embeddings"],
                writes=["similarity_events", "matched_case_state"],
                side_effect=True,
                safety_note="A match still requires Vachan confirmation before final action.",
            ),
            AgentToolSpec(
                name="request_vachan_confirmation",
                purpose="Restate understanding and ask yes/no/partial confirmation before final action.",
                reads=["summary", "resolution", "call_state"],
                writes=["vachan_prompt", "vachan_requested_event"],
                side_effect=True,
                safety_note="No final complaint registration occurs until confirmation is accepted.",
            ),
            AgentToolSpec(
                name="register_complaint",
                purpose="Create structured complaint/action record after confirmed understanding.",
                reads=["confirmed_summary", "resolution", "analysis"],
                writes=["complaints", "complaint_timeline", "call_events"],
                side_effect=True,
                safety_note="Only used after Vachan confirmation for AI-resolved calls.",
            ),
            AgentToolSpec(
                name="route_to_officer",
                purpose="Select best officer by urgency, language/dialect fit, and wait/load signals.",
                reads=["agents", "analysis", "call_state"],
                writes=["handover_context", "officer_matched_event"],
                side_effect=True,
                safety_note="Used for true exception paths, not as a default fallback.",
            ),
            AgentToolSpec(
                name="enqueue_priority_call",
                purpose="Place caller in priority queue when no suitable officer is available.",
                reads=["analysis", "queue_state"],
                writes=["call_queue", "queue_events", "call_state"],
                side_effect=True,
                safety_note="Maintains support path during officer surge.",
            ),
            AgentToolSpec(
                name="respond_to_caller",
                purpose="Generate the next short voice-safe Sahayak response.",
                reads=["phase", "analysis", "transcript", "resolution"],
                writes=["transcript", "response_text"],
                side_effect=True,
                safety_note="Caller-facing response reflects the bounded decision result.",
            ),
        ]

    def specs(self) -> list[AgentToolSpec]:
        return list(self._specs)

    def spec_map(self) -> dict[str, AgentToolSpec]:
        return {spec.name: spec for spec in self._specs}


class SahayakAgentTools:
    """Thin adapters around existing Sahayak modules."""

    def __init__(self, registry: SahayakToolRegistry | None = None):
        self.registry = registry or SahayakToolRegistry()
        self.repository = get_call_repository()

    def load_call_memory(
        self,
        *,
        call_sid: str,
        caller_number: str = "",
        language: str = "",
    ) -> tuple[CallState, AgentToolCall]:
        started_at = time.perf_counter()
        call_state = get_or_create_call(call_sid, caller_number)
        if language:
            call_state.language = language
            self.repository.update_call_state(call_state)
        return call_state, self._call(
            "load_call_memory",
            inputs={"call_sid": call_sid, "caller_number_present": bool(caller_number)},
            outputs={"phase": call_state.current_phase, "language": call_state.language},
            started_at=started_at,
        )

    async def run_decision_pipeline(
        self,
        *,
        call_sid: str,
        text: str,
        caller_number: str = "",
    ) -> tuple[dict[str, Any], AgentToolCall]:
        started_at = time.perf_counter()
        decision = await process_caller_input(
            call_sid=call_sid,
            text=text,
            caller_number=caller_number,
        )
        return decision, self._call(
            "respond_to_caller",
            inputs={"call_sid": call_sid, "text_length": len(text)},
            outputs={
                "action": decision.get("action"),
                "phase": (decision.get("call_state") or {}).get("current_phase"),
            },
            started_at=started_at,
        )

    async def timed_async_tool(
        self,
        name: str,
        function: Callable[..., Awaitable[Any]],
        *args: Any,
        inputs: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> tuple[Any, AgentToolCall]:
        started_at = time.perf_counter()
        result = await function(*args, **kwargs)
        return result, self._call(name, inputs=inputs or {}, outputs={}, started_at=started_at)

    def _call(
        self,
        name: str,
        *,
        inputs: dict[str, Any],
        outputs: dict[str, Any],
        started_at: float,
        status: str = "completed",
    ) -> AgentToolCall:
        spec = self.registry.spec_map().get(name)
        purpose = spec.purpose if spec else name
        return AgentToolCall(
            name=name,
            purpose=purpose,
            status=status,
            inputs_summary=inputs,
            output_summary=outputs,
            duration_ms=round((time.perf_counter() - started_at) * 1000, 2),
        )

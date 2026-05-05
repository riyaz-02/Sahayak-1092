"""Trace construction for Sahayak agent turns."""

from __future__ import annotations

from typing import Any

from backend.agent.context import AgentToolCall, AgentTrace, AgentTurnInput


def infer_domain_tool_calls(decision: dict[str, Any]) -> list[AgentToolCall]:
    """Infer domain tool calls from the bounded decision result.

    The existing decision engine performs several internal tool actions. This
    trace maps the visible output back to the agent tool vocabulary so operators
    can understand what the agent did without reading backend logs.
    """

    calls: list[AgentToolCall] = []
    call_state = decision.get("call_state") or {}
    analysis = decision.get("analysis") or {}
    action = str(decision.get("action") or "")
    phase = str(call_state.get("current_phase") or "")

    calls.append(
        AgentToolCall(
            name="understand_caller",
            purpose="Analyze language, sentiment, urgency, category, and confidence.",
            output_summary={
                "language": analysis.get("language"),
                "category": analysis.get("category"),
                "urgency": analysis.get("urgency"),
                "confidence": analysis.get("confidence"),
                "sentiment": analysis.get("sentiment"),
            },
        )
    )
    calls.append(
        AgentToolCall(
            name="evaluate_safety_policy",
            purpose="Apply deterministic handover and autonomy rules.",
            output_summary={
                "action": action,
                "phase": phase,
                "handover_reason": call_state.get("handover_reason"),
            },
        )
    )

    if decision.get("similarity") or call_state.get("matched_case_id"):
        calls.append(
            AgentToolCall(
                name="search_resolved_cases",
                purpose="Search resolved case memory with vector/local retrieval.",
                output_summary={
                    "matched_case_id": call_state.get("matched_case_id"),
                    "similarity_score": call_state.get("similarity_score"),
                    "similarity_source": call_state.get("similarity_source"),
                },
            )
        )

    if phase in {"vachan_pending", "vachan_partial", "confirming", "clarifying"}:
        calls.append(
            AgentToolCall(
                name="request_vachan_confirmation",
                purpose="Restate understanding and ask for confirmation/correction.",
                output_summary={
                    "phase": phase,
                    "prompt_present": bool(call_state.get("vachan_prompt")),
                },
            )
        )

    if action == "resolve" or call_state.get("complaint_registered"):
        calls.append(
            AgentToolCall(
                name="register_complaint",
                purpose="Create structured complaint/action record after confirmation.",
                output_summary={
                    "complaint_reference_id": call_state.get("complaint_reference_id"),
                    "registered": call_state.get("complaint_registered"),
                },
            )
        )

    if action == "handover":
        calls.append(
            AgentToolCall(
                name="route_to_officer",
                purpose="Route caller to best available officer with warm context.",
                output_summary={
                    "agent_id": call_state.get("agent_id"),
                    "transfer_status": call_state.get("transfer_status"),
                },
            )
        )

    if action == "queue":
        calls.append(
            AgentToolCall(
                name="enqueue_priority_call",
                purpose="Place caller in priority queue during officer surge.",
                output_summary={
                    "queue_entry_id": call_state.get("queue_entry_id"),
                    "position": call_state.get("queue_position"),
                    "priority_score": call_state.get("queue_priority_score"),
                },
            )
        )

    return calls


def build_agent_trace(
    *,
    turn_input: AgentTurnInput,
    decision: dict[str, Any],
    tool_calls: list[AgentToolCall],
    safety_notes: list[str],
    memory_writes: list[str],
) -> AgentTrace:
    call_state = decision.get("call_state") or {}
    trace_calls = list(tool_calls)
    trace_calls.extend(infer_domain_tool_calls(decision))
    return AgentTrace(
        channel=turn_input.channel,
        call_sid=turn_input.call_sid,
        observed_text=turn_input.text,
        final_action=str(decision.get("action") or ""),
        final_phase=str(call_state.get("current_phase") or ""),
        safety_notes=safety_notes,
        memory_writes=memory_writes,
        tool_calls=trace_calls,
    )

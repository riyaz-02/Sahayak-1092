"""Agent-level explanation helpers for bounded safety policy."""

from __future__ import annotations

from typing import Any


class SahayakAgentPolicy:
    """Turn decision outputs into human-readable safety notes."""

    def safety_notes(self, decision: dict[str, Any]) -> list[str]:
        call_state = decision.get("call_state") or {}
        analysis = decision.get("analysis") or {}
        action = str(decision.get("action") or "")
        notes: list[str] = []

        if analysis.get("caller_wants_human"):
            notes.append("Caller explicitly requested a human officer.")
        if float(analysis.get("urgency") or 0.0) >= 0.9:
            notes.append("Extreme urgency threshold was reached.")
        if str(analysis.get("sentiment") or "") in {"distressed", "angry"}:
            notes.append("Distress sentiment was detected.")
        if float(analysis.get("confidence") or 1.0) < 0.5:
            notes.append("Low understanding confidence was detected.")

        phase = str(call_state.get("current_phase") or "")
        if phase in {"vachan_pending", "vachan_partial", "confirming"}:
            notes.append("Vachan confirmation is required before final action.")
        if action == "resolve":
            notes.append("Final action followed a confirmed Vachan loop.")
        elif action == "handover":
            notes.append("Agent escalated to a human officer path.")
        elif action == "queue":
            notes.append("Agent queued caller because no suitable officer was immediately available.")

        if not notes:
            notes.append("No deterministic exception condition blocked autonomous progress.")
        return notes

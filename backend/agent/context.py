"""Agent-facing context and trace schemas."""

from __future__ import annotations

import datetime as dt
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


SAHAYAK_AGENT_GOAL = (
    "Resolve 1092 caller needs safely and quickly: understand the caller, "
    "confirm before final action, execute allowed tools, escalate true "
    "exceptions, and learn from officer corrections."
)


class AgentChannel(str, Enum):
    """Entry channel for one agent turn."""

    API_TEST = "api_test"
    VOICE = "voice"
    DASHBOARD = "dashboard"
    SYSTEM = "system"


class AgentTurnInput(BaseModel):
    """Normalized input for a single Sahayak agent turn."""

    model_config = ConfigDict(extra="forbid")

    call_sid: str
    text: str
    caller_number: str = ""
    language: str = ""
    channel: AgentChannel = AgentChannel.API_TEST
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("call_sid", "text", mode="before")
    @classmethod
    def strip_required_text(cls, value: Any) -> str:
        return str(value or "").strip()

    @field_validator("caller_number", "language", mode="before")
    @classmethod
    def strip_optional_text(cls, value: Any) -> str:
        return str(value or "").strip()


class AgentToolSpec(BaseModel):
    """Static description of an agent tool."""

    model_config = ConfigDict(extra="forbid")

    name: str
    purpose: str
    reads: list[str] = Field(default_factory=list)
    writes: list[str] = Field(default_factory=list)
    side_effect: bool = False
    safety_note: str = ""


class AgentToolCall(BaseModel):
    """One observed tool use in an agent turn trace."""

    model_config = ConfigDict(extra="forbid")

    name: str
    purpose: str
    status: str = "completed"
    inputs_summary: dict[str, Any] = Field(default_factory=dict)
    output_summary: dict[str, Any] = Field(default_factory=dict)
    duration_ms: float | None = None


class AgentTrace(BaseModel):
    """Auditable trace for one bounded agent turn."""

    model_config = ConfigDict(extra="forbid")

    trace_id: str = Field(default_factory=lambda: f"trace-{uuid4()}")
    agent_name: str = "sahayak_1092"
    agent_type: str = "bounded_emergency_operations_agent"
    goal: str = SAHAYAK_AGENT_GOAL
    channel: AgentChannel = AgentChannel.API_TEST
    call_sid: str
    observed_text: str = ""
    final_action: str = ""
    final_phase: str = ""
    safety_notes: list[str] = Field(default_factory=list)
    memory_writes: list[str] = Field(default_factory=list)
    tool_calls: list[AgentToolCall] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: dt.datetime.now(dt.UTC).isoformat())

    def as_event_payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class AgentTurnResult(BaseModel):
    """Decision result plus agent trace metadata."""

    model_config = ConfigDict(extra="allow")

    decision: dict[str, Any]
    trace: AgentTrace
    tools: list[AgentToolSpec] = Field(default_factory=list)

    def as_response(self) -> dict[str, Any]:
        response = dict(self.decision)
        response["agent_trace"] = self.trace.as_event_payload()
        response["agent_tools"] = [tool.model_dump(mode="json") for tool in self.tools]
        return response

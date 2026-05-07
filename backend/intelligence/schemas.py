"""Shared domain schemas for Sahayak 1092.

Call state stays as a small mutable dataclass because it is updated throughout a
live phone call. AI-facing inputs and decision outputs use Pydantic models so
LLM/fallback analysis is bounded, normalized, and auditable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


SUPPORTED_LANGUAGES = {
    "english",
    "hindi",
    "kannada",
    "telugu",
    "tamil",
    "urdu",
    "bengali",
    "marathi",
    "gujarati",
    "punjabi",
    "malayalam",
    "odia",
    "unknown",
}

SUPPORTED_SENTIMENTS = {"calm", "anxious", "distressed", "angry"}

SUPPORTED_CATEGORIES = {
    "theft",
    "accident",
    "domestic",
    "cyber",
    "noise",
    "missing_person",
    "suspicious_activity",
    "medical",
    "fire",
    "traffic",
    "harassment",
    "civic",
    "general",
}


def _normalize_label(value: str) -> str:
    return value.strip().lower().replace("-", "_").replace(" ", "_")


class CallOutcome(str, Enum):
    AI_RESOLVED = "ai_resolved"
    HANDED_OVER = "handed_over"
    QUEUED = "queued"
    IN_PROGRESS = "in_progress"


class HandoverReason(str, Enum):
    LOW_CONFIDENCE = "low_confidence_after_retries"
    CALLER_REQUESTED = "caller_requested_human"
    HIGH_URGENCY = "extreme_urgency_distress"


class CallPhase(str, Enum):
    GREETING = "greeting"
    LISTENING = "listening"
    CONFIRMING = "confirming"
    COLLECTING_ISSUE = "collecting_issue"
    CLARIFYING = "clarifying"
    VACHAN_PENDING = "vachan_pending"
    VACHAN_PARTIAL = "vachan_partial"
    RESOLVED = "resolved"
    HANDOVER = "handover"
    HANDOVER_PENDING = "handover_pending"
    QUEUED = "queued"


class ConfirmationStatus(str, Enum):
    NONE = "none"
    YES = "yes"
    NO = "no"
    PARTIAL = "partial"


class DecisionAction(str, Enum):
    CONTINUE = "continue"
    RESOLVE = "resolve"
    HANDOVER = "handover"
    QUEUE = "queue"
    IVR_REDIRECT = "ivr_redirect"


class CallAnalysis(BaseModel):
    """Validated result of analysing one caller utterance."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    language: str = Field(default="english")
    dialect: str = Field(default="", max_length=80)
    sentiment: str = Field(default="calm")
    urgency: float = Field(default=0.5, ge=0.0, le=1.0)
    confidence: float = Field(default=0.7, ge=0.0, le=1.0)
    category: str = Field(default="general")
    summary: str = Field(default="", max_length=500)
    caller_wants_human: bool = Field(default=False)
    is_confirmation: Optional[bool] = Field(default=None)
    confirmation_status: str = Field(default=ConfirmationStatus.NONE.value)
    correction_text: str = Field(default="", max_length=800)
    missing_fields: list[str] = Field(default_factory=list)
    raw_text: str = Field(default="", max_length=3000)

    @field_validator("language", mode="before")
    @classmethod
    def normalize_language(cls, value: Any) -> str:
        aliases = {
            "en": "english",
            "eng": "english",
            "hi": "hindi",
            "hin": "hindi",
            "kn": "kannada",
            "kan": "kannada",
            "te": "telugu",
            "tel": "telugu",
            "ta": "tamil",
            "tam": "tamil",
            "ur": "urdu",
            "bn": "bengali",
            "ben": "bengali",
            "mr": "marathi",
            "mar": "marathi",
            "gu": "gujarati",
            "guj": "gujarati",
            "pa": "punjabi",
            "pun": "punjabi",
            "ml": "malayalam",
            "mal": "malayalam",
            "or": "odia",
            "od": "odia",
        }
        label = _normalize_label(str(value or "english"))
        return aliases.get(label, label if label in SUPPORTED_LANGUAGES else "unknown")

    @field_validator("sentiment", mode="before")
    @classmethod
    def normalize_sentiment(cls, value: Any) -> str:
        label = _normalize_label(str(value or "calm"))
        if label in {"frustrated", "fearful", "panic", "panicked", "scared"}:
            return "distressed"
        return label if label in SUPPORTED_SENTIMENTS else "calm"

    @field_validator("category", mode="before")
    @classmethod
    def normalize_category(cls, value: Any) -> str:
        label = _normalize_label(str(value or "general"))
        aliases = {
            "mobile_theft": "theft",
            "robbery": "theft",
            "lost_property": "theft",
            "cyber_fraud": "cyber",
            "domestic_violence": "domestic",
            "road_accident": "accident",
            "medical_emergency": "medical",
            "suspicious": "suspicious_activity",
        }
        label = aliases.get(label, label)
        return label if label in SUPPORTED_CATEGORIES else "general"

    @field_validator("confirmation_status", mode="before")
    @classmethod
    def normalize_confirmation_status(cls, value: Any) -> str:
        label = _normalize_label(str(value or ConfirmationStatus.NONE.value))
        allowed = {item.value for item in ConfirmationStatus}
        return label if label in allowed else ConfirmationStatus.NONE.value

    @field_validator("summary", mode="before")
    @classmethod
    def normalize_summary(cls, value: Any) -> str:
        return str(value or "").strip()

    def as_event_payload(self) -> dict[str, Any]:
        """Return a JSON-safe dict for audit logs and repository storage."""

        return self.model_dump(mode="json")


class SimilarityMatch(BaseModel):
    """Retrieved resolved-case match used by Smart Similarity Detection."""

    model_config = ConfigDict(extra="allow")

    matched_case_id: str
    matched_case: dict[str, Any]
    similarity_score: float = Field(ge=0.0, le=1.0)
    adapted_resolution: str
    retrieval_source: str = Field(default="local_fallback")
    retrieval_signals: dict[str, Any] = Field(default_factory=dict)

    def as_event_payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class HandoverContext(BaseModel):
    """Context packet sent to a human officer during warm handover."""

    model_config = ConfigDict(extra="allow")

    call_sid: str
    caller_number: str = ""
    transcript: list[dict[str, Any]] = Field(default_factory=list)
    ai_summary: str = ""
    sentiment: str = "calm"
    urgency: float = Field(default=0.5, ge=0.0, le=1.0)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    language: str = "english"
    dialect: str = ""
    category: str = "general"
    handover_reason: str = ""
    selected_agent: dict[str, Any] = Field(default_factory=dict)
    routing_score: float = Field(default=0.0, ge=0.0, le=1.0)
    routing_score_breakdown: dict[str, Any] = Field(default_factory=dict)
    ranked_agents: list[dict[str, Any]] = Field(default_factory=list)
    officer_first_sentence: str = ""

    def as_event_payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class DecisionResult(BaseModel):
    """Validated output of the master decision pipeline."""

    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    response_text: str
    action: DecisionAction
    call_state: dict[str, Any]
    analysis: CallAnalysis | None = None
    agent: dict[str, Any] | None = None
    handover_context: dict[str, Any] | None = None
    similarity: SimilarityMatch | None = None
    reason: str | None = None

    def as_response(self) -> dict[str, Any]:
        """Return the existing dict shape expected by FastAPI and tests."""

        return self.model_dump(mode="json", exclude_none=True)


@dataclass
class CallState:
    """Mutable state for a single active call."""

    call_sid: str = ""
    caller_number: str = ""
    language: str = "hindi"
    dialect: str = ""
    transcript: list[dict[str, Any]] = field(default_factory=list)
    analyses: list[dict[str, Any]] = field(default_factory=list)
    current_phase: str = CallPhase.COLLECTING_ISSUE.value
    attempt_count: int = 0
    ai_summary: str = ""
    resolution: str = ""
    vachan_prompt: str = ""
    vachan_corrections: list[dict[str, Any]] = field(default_factory=list)
    pending_clarification_fields: list[str] = field(default_factory=list)
    similar_case: Optional[dict[str, Any]] = None
    matched_case_id: Optional[str] = None
    similarity_score: Optional[float] = None
    similarity_source: str = ""
    adapted_resolution: str = ""
    agent_id: Optional[str] = None
    handover_context: dict[str, Any] = field(default_factory=dict)
    routing_score_breakdown: dict[str, Any] = field(default_factory=dict)
    officer_first_sentence: str = ""
    handover_accepted_by: Optional[str] = None
    handover_accepted_at: Optional[str] = None
    transfer_status: str = ""
    transfer_mode: str = ""
    queue_entry_id: Optional[str] = None
    queue_status: str = ""
    queue_position: Optional[int] = None
    queue_priority_score: Optional[float] = None
    queue_estimated_wait_sec: Optional[int] = None
    queue_service_target: str = ""
    high_help_alert_at: Optional[str] = None
    outcome: Optional[CallOutcome] = None
    handover_reason: Optional[HandoverReason] = None
    complaint_registered: bool = False
    complaint_reference_id: Optional[str] = None
    queue_start_time: Optional[float] = None


@dataclass(frozen=True)
class HandoverDecision:
    """Decision emitted by the deterministic safety policy."""

    needs_handover: bool = False
    reason: Optional[HandoverReason] = None
    attempt_increment: int = 0
    explanation: str = ""

"""Call-state repository with Supabase, Redis, and local fallback support."""

from __future__ import annotations

import copy
import datetime as dt
import json
from dataclasses import asdict, is_dataclass
from enum import Enum
from threading import RLock
from typing import Any
from uuid import uuid4

from pydantic import BaseModel

from backend.config import Settings, get_settings
from backend.intelligence.schemas import CallAnalysis, CallOutcome, CallState, HandoverReason
from backend import supabase_client as db


CALL_EVENT_TYPES = {
    "call_started",
    "agent_turn_started",
    "agent_tool_used",
    "agent_turn_completed",
    "greeting_sent",
    "utterance_received",
    "stt_completed",
    "stt_failed",
    "analysis_completed",
    "similarity_search_completed",
    "similarity_match_found",
    "vachan_requested",
    "vachan_confirmed",
    "vachan_rejected",
    "vachan_partial",
    "vachan_correction_requested",
    "ai_correction_applied",
    "complaint_registered",
    "complaint_timeline_updated",
    "knowledge_base_case_added",
    "handover_requested",
    "officer_matched",
    "handover_accepted",
    "transfer_initiated",
    "transfer_completed",
    "transfer_failed",
    "queued",
    "queue_updated",
    "dtmf_redirect",
    "high_help_alert",
    "tts_completed",
    "voice_turn_completed",
    "call_completed",
}


def _utc_now() -> str:
    return dt.datetime.now(dt.UTC).isoformat()


def _json_safe(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, BaseModel):
        return _json_safe(value.model_dump(mode="json"))
    if is_dataclass(value):
        return _json_safe(asdict(value))
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    return value


def state_to_dict(call_state: CallState) -> dict[str, Any]:
    return _json_safe(asdict(call_state))


def state_from_dict(data: dict[str, Any]) -> CallState:
    safe = copy.deepcopy(data)
    if safe.get("outcome") and not isinstance(safe["outcome"], CallOutcome):
        safe["outcome"] = CallOutcome(safe["outcome"])
    if safe.get("handover_reason") and not isinstance(safe["handover_reason"], HandoverReason):
        safe["handover_reason"] = HandoverReason(safe["handover_reason"])
    return CallState(**safe)


def _value(value: Any) -> Any:
    return value.value if isinstance(value, Enum) else value


class RedisLiveStateStore:
    """Optional Redis-backed live call state.

    The app falls back silently when Redis is not configured or unavailable.
    """

    def __init__(self, redis_url: str):
        import redis

        self._client = redis.Redis.from_url(redis_url, decode_responses=True)
        self._client.ping()

    @staticmethod
    def create(redis_url: str) -> "RedisLiveStateStore | None":
        if not redis_url:
            return None
        try:
            return RedisLiveStateStore(redis_url)
        except Exception as exc:
            print(f"[WARN] Redis live state disabled: {exc}")
            return None

    @staticmethod
    def _state_key(call_sid: str) -> str:
        return f"sahayak1092:call_state:{call_sid}"

    def set_state(self, call_state: CallState) -> None:
        self._client.set(self._state_key(call_state.call_sid), json.dumps(state_to_dict(call_state)))

    def get_state(self, call_sid: str) -> CallState | None:
        raw = self._client.get(self._state_key(call_sid))
        if not raw:
            return None
        try:
            return state_from_dict(json.loads(raw))
        except Exception:
            return None

    def delete_state(self, call_sid: str) -> None:
        self._client.delete(self._state_key(call_sid))

    def list_states(self) -> list[CallState]:
        states: list[CallState] = []
        for key in self._client.scan_iter("sahayak1092:call_state:*"):
            raw = self._client.get(key)
            if not raw:
                continue
            try:
                states.append(state_from_dict(json.loads(raw)))
            except Exception:
                continue
        return states

    def health_check(self) -> dict[str, Any]:
        return {"configured": True, "available": bool(self._client.ping())}


class CallStateRepository:
    """Repository for live call state, call logs, transcripts, and audit events."""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self._lock = RLock()
        self._states: dict[str, CallState] = {}
        self._records: dict[str, dict[str, Any]] = {}
        self._events: dict[str, list[dict[str, Any]]] = {}
        self._redis = RedisLiveStateStore.create(self.settings.redis_url)

    def health_check(self) -> dict[str, object]:
        redis_health = {"configured": bool(self.settings.redis_url), "available": False}
        if self._redis:
            try:
                redis_health = self._redis.health_check()
            except Exception:
                redis_health = {"configured": True, "available": False}
        return {
            "local_fallback": True,
            "supabase_configured": self.settings.supabase_configured,
            "supabase": db.supabase_health(probe=False),
            "vector_db": db.vector_db_health(
                embedding_dimension=self.settings.embedding_dimension,
                probe=False,
            ),
            "redis": redis_health,
            "local_active_calls": len(self._states),
        }

    def create_call_state(self, call_state: CallState) -> dict[str, Any]:
        with self._lock:
            existing = self._records.get(call_state.call_sid)
            self._states[call_state.call_sid] = copy.deepcopy(call_state)
            self._records.setdefault(
                call_state.call_sid,
                {
                    "id": str(uuid4()),
                    "call_sid": call_state.call_sid,
                    "caller_number": call_state.caller_number,
                    "language": call_state.language,
                    "dialect": call_state.dialect,
                    "transcript": [],
                    "ai_summary": call_state.ai_summary,
                    "outcome": None,
                    "similar_case": call_state.matched_case_id,
                    "similarity_score": call_state.similarity_score,
                    "similarity_source": call_state.similarity_source,
                    "adapted_resolution": call_state.adapted_resolution,
                    "complaint_reference_id": call_state.complaint_reference_id,
                    "handover_context": copy.deepcopy(call_state.handover_context),
                    "routing_score_breakdown": copy.deepcopy(call_state.routing_score_breakdown),
                    "officer_first_sentence": call_state.officer_first_sentence,
                    "transfer_status": call_state.transfer_status,
                    "transfer_mode": call_state.transfer_mode,
                    "handover_accepted_by": call_state.handover_accepted_by,
                    "handover_accepted_at": call_state.handover_accepted_at,
                    "queue_entry_id": call_state.queue_entry_id,
                    "queue_status": call_state.queue_status,
                    "queue_position": call_state.queue_position,
                    "queue_priority_score": call_state.queue_priority_score,
                    "queue_estimated_wait_sec": call_state.queue_estimated_wait_sec,
                    "queue_service_target": call_state.queue_service_target,
                    "high_help_alert_at": call_state.high_help_alert_at,
                    "created_at": _utc_now(),
                    "updated_at": _utc_now(),
                },
            )

        if self._redis:
            self._safe_redis_set(call_state)

        if not existing and self.settings.supabase_configured:
            try:
                db.create_call_log(call_state.call_sid, call_state.caller_number)
            except Exception:
                pass
        return copy.deepcopy(self._records[call_state.call_sid])

    def update_call_state(self, call_state: CallState, analysis: CallAnalysis | None = None) -> dict[str, Any]:
        with self._lock:
            self._states[call_state.call_sid] = copy.deepcopy(call_state)
            record = self._records.setdefault(
                call_state.call_sid,
                {
                    "id": str(uuid4()),
                    "call_sid": call_state.call_sid,
                    "caller_number": call_state.caller_number,
                    "created_at": _utc_now(),
                },
            )
            record.update(
                {
                    "caller_number": call_state.caller_number,
                    "language": call_state.language,
                    "dialect": call_state.dialect,
                    "transcript": copy.deepcopy(call_state.transcript),
                    "ai_summary": call_state.ai_summary,
                    "outcome": _value(call_state.outcome) if call_state.outcome else None,
                    "agent_id": call_state.agent_id,
                    "similar_case": call_state.matched_case_id,
                    "similarity_score": call_state.similarity_score,
                    "similarity_source": call_state.similarity_source,
                    "adapted_resolution": call_state.adapted_resolution,
                    "complaint_reference_id": call_state.complaint_reference_id,
                    "handover_context": copy.deepcopy(call_state.handover_context),
                    "routing_score_breakdown": copy.deepcopy(call_state.routing_score_breakdown),
                    "officer_first_sentence": call_state.officer_first_sentence,
                    "transfer_status": call_state.transfer_status,
                    "transfer_mode": call_state.transfer_mode,
                    "handover_accepted_by": call_state.handover_accepted_by,
                    "handover_accepted_at": call_state.handover_accepted_at,
                    "queue_entry_id": call_state.queue_entry_id,
                    "queue_status": call_state.queue_status,
                    "queue_position": call_state.queue_position,
                    "queue_priority_score": call_state.queue_priority_score,
                    "queue_estimated_wait_sec": call_state.queue_estimated_wait_sec,
                    "queue_service_target": call_state.queue_service_target,
                    "high_help_alert_at": call_state.high_help_alert_at,
                    "current_phase": call_state.current_phase,
                    "updated_at": _utc_now(),
                }
            )
            if analysis:
                record.update(
                    {
                        "sentiment": analysis.sentiment,
                        "urgency": analysis.urgency,
                        "confidence": analysis.confidence,
                        "category": analysis.category,
                    }
                )

        if self._redis:
            self._safe_redis_set(call_state)

        try:
            fields = {
                "language": call_state.language,
                "dialect": call_state.dialect,
                "transcript": call_state.transcript,
                "ai_summary": call_state.ai_summary,
                "outcome": _value(call_state.outcome) if call_state.outcome else None,
                "agent_id": call_state.agent_id,
                "similar_case": call_state.matched_case_id,
                "similarity_score": call_state.similarity_score,
                "similarity_source": call_state.similarity_source,
                "adapted_resolution": call_state.adapted_resolution,
                "complaint_reference_id": call_state.complaint_reference_id,
                "handover_context": call_state.handover_context,
                "routing_score_breakdown": call_state.routing_score_breakdown,
                "officer_first_sentence": call_state.officer_first_sentence,
                "transfer_status": call_state.transfer_status,
                "transfer_mode": call_state.transfer_mode,
                "handover_accepted_by": call_state.handover_accepted_by,
                "handover_accepted_at": call_state.handover_accepted_at,
                "queue_entry_id": call_state.queue_entry_id,
                "queue_status": call_state.queue_status,
                "queue_position": call_state.queue_position,
                "queue_priority_score": call_state.queue_priority_score,
                "queue_estimated_wait_sec": call_state.queue_estimated_wait_sec,
                "queue_service_target": call_state.queue_service_target,
                "high_help_alert_at": call_state.high_help_alert_at,
            }
            if analysis:
                fields.update(
                    {
                        "sentiment": analysis.sentiment,
                        "urgency": analysis.urgency,
                        "confidence": analysis.confidence,
                    }
                )
            if self.settings.supabase_configured:
                db.update_call_log(call_sid=call_state.call_sid, **fields)
        except Exception:
            pass

        return copy.deepcopy(self._records[call_state.call_sid])

    def get_call_state(self, call_sid: str) -> CallState | None:
        with self._lock:
            if call_sid in self._states:
                return copy.deepcopy(self._states[call_sid])
        if self._redis:
            try:
                state = self._redis.get_state(call_sid)
                if state:
                    with self._lock:
                        self._states[call_sid] = copy.deepcopy(state)
                    return state
            except Exception:
                pass
        return None

    def remove_call_state(self, call_sid: str) -> None:
        with self._lock:
            self._states.pop(call_sid, None)
        if self._redis:
            try:
                self._redis.delete_state(call_sid)
            except Exception:
                pass

    def append_call_event(
        self,
        call_sid: str,
        event_type: str,
        payload: dict[str, Any] | None = None,
        call_state: CallState | None = None,
        analysis: CallAnalysis | None = None,
    ) -> dict[str, Any]:
        if event_type not in CALL_EVENT_TYPES:
            raise ValueError(f"Unknown call event type: {event_type}")

        event = {
            "id": str(uuid4()),
            "call_sid": call_sid,
            "event_type": event_type,
            "payload": _json_safe(payload or {}),
            "phase": call_state.current_phase if call_state else None,
            "language": call_state.language if call_state else None,
            "dialect": call_state.dialect if call_state else None,
            "urgency": analysis.urgency if analysis else None,
            "confidence": analysis.confidence if analysis else None,
            "created_at": _utc_now(),
        }

        with self._lock:
            self._events.setdefault(call_sid, []).append(copy.deepcopy(event))

        if self.settings.supabase_configured:
            try:
                db.insert_call_event(event)
            except Exception:
                pass

        return copy.deepcopy(event)

    def fetch_active_calls(self) -> list[dict[str, Any]]:
        states: list[CallState] = []
        with self._lock:
            states.extend(copy.deepcopy(list(self._states.values())))
        if not states and self._redis:
            try:
                states = self._redis.list_states()
            except Exception:
                states = []
        return [self._state_summary(state) for state in states]

    def fetch_recent_calls(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            records = list(self._records.values())
        if records:
            records.sort(key=lambda item: item.get("created_at", ""), reverse=True)
            return copy.deepcopy(records[:limit])
        try:
            return db.get_recent_calls(limit=limit)
        except Exception:
            return []

    def fetch_call_transcript(self, call_sid: str) -> list[dict[str, Any]]:
        state = self.get_call_state(call_sid)
        if state:
            return copy.deepcopy(state.transcript)
        with self._lock:
            record = self._records.get(call_sid)
            if record:
                transcript = record.get("transcript") or []
                if isinstance(transcript, str):
                    try:
                        return json.loads(transcript)
                    except Exception:
                        return []
                return copy.deepcopy(transcript)
        try:
            call_log = db.get_call_log(call_sid)
            if call_log:
                transcript = call_log.get("transcript") or []
                if isinstance(transcript, str):
                    return json.loads(transcript)
                return transcript
        except Exception:
            pass
        return []

    def fetch_call_events(self, call_sid: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock:
            if call_sid:
                events = self._events.get(call_sid, [])
            else:
                events = [event for event_list in self._events.values() for event in event_list]
        if events:
            events = sorted(events, key=lambda event: event.get("created_at", ""), reverse=True)
            return copy.deepcopy(events[:limit])
        try:
            return db.get_call_events(call_sid=call_sid, limit=limit)
        except Exception:
            return []

    def reset_for_tests(self) -> None:
        with self._lock:
            self._states.clear()
            self._records.clear()
            self._events.clear()

    def _safe_redis_set(self, call_state: CallState) -> None:
        try:
            self._redis.set_state(call_state)
        except Exception:
            pass

    @staticmethod
    def _state_summary(state: CallState) -> dict[str, Any]:
        latest_analysis = state.analyses[-1] if state.analyses else {}
        return {
            "call_sid": state.call_sid,
            "caller_number": state.caller_number,
            "language": state.language,
            "dialect": state.dialect,
            "category": latest_analysis.get("category", "general"),
            "sentiment": latest_analysis.get("sentiment", "calm"),
            "urgency": latest_analysis.get("urgency", 0.0),
            "confidence": latest_analysis.get("confidence", 0.0),
            "phase": state.current_phase,
            "ai_summary": state.ai_summary,
            "matched_case_id": state.matched_case_id,
            "similarity_score": state.similarity_score,
            "similarity_source": state.similarity_source,
            "adapted_resolution": state.adapted_resolution,
            "complaint_registered": state.complaint_registered,
            "complaint_reference_id": state.complaint_reference_id,
            "handover_context": copy.deepcopy(state.handover_context),
            "routing_score_breakdown": copy.deepcopy(state.routing_score_breakdown),
            "officer_first_sentence": state.officer_first_sentence,
            "transfer_status": state.transfer_status,
            "transfer_mode": state.transfer_mode,
            "handover_accepted_by": state.handover_accepted_by,
            "handover_accepted_at": state.handover_accepted_at,
            "queue_entry_id": state.queue_entry_id,
            "queue_status": state.queue_status,
            "queue_position": state.queue_position,
            "queue_priority_score": state.queue_priority_score,
            "queue_estimated_wait_sec": state.queue_estimated_wait_sec,
            "queue_service_target": state.queue_service_target,
            "high_help_alert_at": state.high_help_alert_at,
            "transcript_count": len(state.transcript),
            "outcome": _value(state.outcome) if state.outcome else None,
            "agent_id": state.agent_id,
        }


call_repository = CallStateRepository()


def get_call_repository() -> CallStateRepository:
    return call_repository

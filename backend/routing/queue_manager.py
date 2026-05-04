"""Priority queue manager for surge handover cases."""

from __future__ import annotations

import datetime as dt
from dataclasses import asdict, dataclass
from threading import RLock
from typing import Any
from uuid import uuid4

from backend import supabase_client as db
from backend.config import Settings, get_settings
from backend.intelligence.schemas import CallAnalysis, CallState


QUEUE_STATUS_WAITING = "waiting"
QUEUE_STATUS_REDIRECTED = "redirected"
QUEUE_STATUS_HIGH_HELP_ALERT = "high_help_alert"
QUEUE_STATUS_RESOLVED = "resolved"

DTMF_SERVICE_MAP = {
    "1": {"service": "Police", "target": "police", "phone": "100"},
    "2": {"service": "Ambulance", "target": "ambulance", "phone": "108"},
    "3": {"service": "Fire Services", "target": "fire", "phone": "101"},
}


def _utc_now() -> str:
    return dt.datetime.now(dt.UTC).isoformat()


def _parse_time(value: str | None) -> dt.datetime:
    if not value:
        return dt.datetime.now(dt.UTC)
    try:
        parsed = dt.datetime.fromisoformat(value)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.UTC)
    except ValueError:
        return dt.datetime.now(dt.UTC)


def calculate_priority_score(analysis: CallAnalysis, reason: str = "") -> float:
    """Score queued calls so urgent/distressed cases rise to the top."""

    urgency = max(0.0, min(float(analysis.urgency or 0.5), 1.0))
    confidence = max(0.0, min(float(analysis.confidence or 0.5), 1.0))
    distress = 1.0 if analysis.sentiment in {"distressed", "angry"} else 0.35
    reason_boost = 0.12 if reason in {"extreme_urgency_distress", "caller_requested_human"} else 0.0
    score = 0.62 * urgency + 0.22 * distress + 0.10 * confidence + reason_boost
    return round(max(0.0, min(score, 1.0)), 4)


@dataclass
class QueueEntry:
    """Durable queue entry visible to dashboard and audit logs."""

    id: str
    call_sid: str
    caller_number: str
    language: str
    dialect: str
    category: str
    urgency: float
    sentiment: str
    confidence: float
    priority_score: float
    status: str = QUEUE_STATUS_WAITING
    reason: str = ""
    position: int = 1
    estimated_wait_sec: int = 0
    service_target: str = ""
    dtmf_digit: str = ""
    high_help_alert_at: str | None = None
    created_at: str = ""
    updated_at: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class PriorityQueueManager:
    """Queue facade with local fallback and optional Supabase persistence."""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self._lock = RLock()
        self._entries: dict[str, QueueEntry] = {}

    def reset_for_tests(self) -> None:
        with self._lock:
            self._entries.clear()

    def enqueue_call(
        self,
        call_state: CallState,
        analysis: CallAnalysis,
        *,
        reason: str = "",
    ) -> QueueEntry:
        """Create or update a waiting queue entry for a call."""

        existing = self.get_entry(call_state.call_sid)
        if existing and existing.status == QUEUE_STATUS_WAITING:
            return existing

        now = _utc_now()
        entry = QueueEntry(
            id=str(uuid4()),
            call_sid=call_state.call_sid,
            caller_number=call_state.caller_number,
            language=call_state.language or analysis.language,
            dialect=call_state.dialect or analysis.dialect,
            category=analysis.category,
            urgency=analysis.urgency,
            sentiment=analysis.sentiment,
            confidence=analysis.confidence,
            priority_score=calculate_priority_score(analysis, reason),
            reason=reason,
            created_at=now,
            updated_at=now,
        )
        with self._lock:
            self._entries[entry.call_sid] = entry
            self._recompute_positions_locked()
            entry = self._entries[entry.call_sid]

        self._persist_entry(entry)
        return entry

    def redirect_to_service(self, call_sid: str, digit: str) -> QueueEntry | None:
        """Mark a queued call as redirected through surge IVR."""

        service = DTMF_SERVICE_MAP.get(digit)
        if not service:
            return None
        with self._lock:
            entry = self._entries.get(call_sid)
            if not entry:
                entry = self._entry_from_db(call_sid)
                if not entry:
                    return None
                self._entries[call_sid] = entry
            entry.status = QUEUE_STATUS_REDIRECTED
            entry.service_target = service["target"]
            entry.dtmf_digit = digit
            entry.updated_at = _utc_now()
            self._recompute_positions_locked()
            updated = self._entries[call_sid]

        self._persist_entry(updated)
        return updated

    def mark_high_help_alert(self, call_sid: str) -> QueueEntry | None:
        """Mark a waiting call as a High-Help Alert."""

        with self._lock:
            entry = self._entries.get(call_sid)
            if not entry:
                entry = self._entry_from_db(call_sid)
                if not entry:
                    return None
                self._entries[call_sid] = entry
            entry.status = QUEUE_STATUS_HIGH_HELP_ALERT
            entry.service_target = "police"
            entry.high_help_alert_at = _utc_now()
            entry.updated_at = entry.high_help_alert_at
            self._recompute_positions_locked()
            updated = self._entries[call_sid]

        self._persist_entry(updated)
        return updated

    def complete_entry(self, call_sid: str) -> QueueEntry | None:
        """Mark a queue entry resolved/removed from active waiting queue."""

        with self._lock:
            entry = self._entries.get(call_sid)
            if not entry:
                return None
            entry.status = QUEUE_STATUS_RESOLVED
            entry.updated_at = _utc_now()
            self._recompute_positions_locked()
            updated = self._entries[call_sid]
        self._persist_entry(updated)
        return updated

    def get_entry(self, call_sid: str) -> QueueEntry | None:
        with self._lock:
            entry = self._entries.get(call_sid)
            if entry:
                return QueueEntry(**entry.as_dict())
        return self._entry_from_db(call_sid)

    def list_entries(
        self,
        *,
        include_inactive: bool = False,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """List queue entries sorted by waiting priority and age."""

        with self._lock:
            entries = [QueueEntry(**entry.as_dict()) for entry in self._entries.values()]
        if not entries:
            entries = self._entries_from_db(limit=limit)
        if not include_inactive:
            entries = [entry for entry in entries if entry.status == QUEUE_STATUS_WAITING]
        entries.sort(key=lambda item: (-item.priority_score, _parse_time(item.created_at)))
        return [entry.as_dict() for entry in entries[:limit]]

    def apply_to_call_state(self, call_state: CallState, entry: QueueEntry | None) -> CallState:
        """Copy queue metadata onto call state."""

        if not entry:
            return call_state
        call_state.queue_entry_id = entry.id
        call_state.queue_status = entry.status
        call_state.queue_position = entry.position
        call_state.queue_priority_score = entry.priority_score
        call_state.queue_estimated_wait_sec = entry.estimated_wait_sec
        call_state.queue_service_target = entry.service_target
        call_state.high_help_alert_at = entry.high_help_alert_at
        return call_state

    def queue_timeout_sec(self) -> int:
        return self.settings.effective_high_help_alert_timeout_sec

    def _recompute_positions_locked(self) -> None:
        waiting = [
            entry for entry in self._entries.values()
            if entry.status == QUEUE_STATUS_WAITING
        ]
        waiting.sort(key=lambda item: (-item.priority_score, _parse_time(item.created_at)))
        for index, entry in enumerate(waiting, start=1):
            entry.position = index
            entry.estimated_wait_sec = max(0, (index - 1) * 45)
            entry.updated_at = entry.updated_at or _utc_now()

    def _persist_entry(self, entry: QueueEntry) -> None:
        if not self.settings.supabase_configured:
            return
        try:
            db.upsert_queue_entry(entry.as_dict())
        except Exception:
            pass

    def _entry_from_db(self, call_sid: str) -> QueueEntry | None:
        if not self.settings.supabase_configured:
            return None
        try:
            row = db.get_queue_entry(call_sid)
            return QueueEntry(**row) if row else None
        except Exception:
            return None

    def _entries_from_db(self, limit: int = 50) -> list[QueueEntry]:
        if not self.settings.supabase_configured:
            return []
        try:
            return [QueueEntry(**row) for row in db.get_queue_entries(limit=limit)]
        except Exception:
            return []


queue_manager = PriorityQueueManager()


def get_queue_manager() -> PriorityQueueManager:
    return queue_manager

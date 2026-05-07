"""Structured complaint and action registry for AI-resolved calls."""

from __future__ import annotations

import datetime as dt
import re
from threading import RLock
from typing import Any
from uuid import uuid4

from backend import supabase_client as db
from backend.config import Settings, get_settings
from backend.intelligence.schemas import CallAnalysis, CallState


COMPLAINT_TIMELINE_EVENT_TYPES = {
    "complaint_registered",
    "government_payload_created",
    "status_updated",
    "note_added",
    "officer_action",
    "complaint_resolved",
}


def _utc_now() -> str:
    return dt.datetime.now(dt.UTC).isoformat()


def _safe_token(value: str, default: str = "GEN") -> str:
    token = re.sub(r"[^A-Z0-9]", "", (value or "").upper())
    return token[:3] or default


def generate_complaint_reference(call_sid: str, category: str, created_at: str | None = None) -> str:
    """Generate a readable complaint reference suitable for citizens/officers."""

    timestamp = created_at or _utc_now()
    try:
        day = dt.datetime.fromisoformat(timestamp).strftime("%Y%m%d")
    except ValueError:
        day = dt.datetime.now(dt.UTC).strftime("%Y%m%d")
    suffix = re.sub(r"[^A-Z0-9]", "", (call_sid or uuid4().hex).upper())[-6:]
    return f"SAH-{_safe_token(category)}-{day}-{suffix}"


def extract_location(text: str) -> str:
    """Extract a best-effort location phrase from caller text or summary."""

    clean = " ".join((text or "").strip().split())
    if not clean:
        return ""

    patterns = [
        r"\b(?:at|near|in|from|outside|inside)\s+([A-Za-z0-9][A-Za-z0-9 .,'/-]{2,90})",
        r"\b(?:location is|place is)\s+([A-Za-z0-9][A-Za-z0-9 .,'/-]{2,90})",
    ]
    stop_words = {
        "while",
        "when",
        "and",
        "but",
        "please",
        "kindly",
        "yesterday",
        "today",
        "now",
    }
    for pattern in patterns:
        match = re.search(pattern, clean, flags=re.IGNORECASE)
        if not match:
            continue
        location = match.group(1).strip(" .,")
        words = location.split()
        trimmed: list[str] = []
        for word in words:
            if word.lower().strip(".,") in stop_words:
                break
            trimmed.append(word.strip(".,"))
        location = " ".join(trimmed).strip(" .,")
        if location:
            return location[:120]
    return ""


def urgency_band(urgency: float | None) -> str:
    value = urgency if urgency is not None else 0.5
    if value >= 0.9:
        return "critical"
    if value >= 0.7:
        return "high"
    if value >= 0.4:
        return "medium"
    return "low"


def build_government_payload(record: dict[str, Any], resolution: str = "") -> dict[str, Any]:
    """Build the mock government registration payload used in demos."""

    return {
        "system": "sahayak_1092_mock_government_registry",
        "action": "register_complaint",
        "status": "accepted_for_demo",
        "submitted_at": _utc_now(),
        "priority": urgency_band(record.get("urgency")),
        "reference_id": record["reference_id"],
        "payload": {
            "category": record.get("category"),
            "description": record.get("description"),
            "location": record.get("location"),
            "urgency": record.get("urgency"),
            "language": record.get("language"),
            "dialect": record.get("dialect"),
            "call_sid": record.get("call_sid"),
            "transcript_ref": record.get("transcript_ref"),
            "recommended_action": resolution,
        },
    }


class ComplaintRegistry:
    """Complaint storage facade with Supabase and local fallback behavior."""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self._lock = RLock()
        self._records: dict[str, dict[str, Any]] = {}
        self._timelines: dict[str, list[dict[str, Any]]] = {}

    def reset_for_tests(self) -> None:
        with self._lock:
            self._records.clear()
            self._timelines.clear()

    def register_ai_resolved_complaint(
        self,
        *,
        call_state: CallState,
        analysis: CallAnalysis,
        category: str,
        resolution: str,
    ) -> dict[str, Any]:
        """Create a structured complaint/action record for a confirmed AI resolution."""

        existing = self.get_by_call_sid(call_state.call_sid)
        if existing:
            return existing

        created_at = _utc_now()
        reference_id = generate_complaint_reference(call_state.call_sid, category, created_at)
        description = call_state.ai_summary or analysis.summary or analysis.raw_text
        location = extract_location(" ".join([analysis.raw_text, analysis.summary, call_state.ai_summary]))
        transcript_ref = f"call_logs.call_sid:{call_state.call_sid}:transcript"
        record = {
            "id": str(uuid4()),
            "reference_id": reference_id,
            "call_log_id": None,
            "call_sid": call_state.call_sid,
            "caller_number": call_state.caller_number or "",
            "category": category or analysis.category or "general",
            "description": description,
            "location": location,
            "urgency": analysis.urgency,
            "language": call_state.language or analysis.language,
            "dialect": call_state.dialect or analysis.dialect,
            "transcript_ref": transcript_ref,
            "status": "registered",
            "assigned_agent": call_state.agent_id,
            "source": "ai_resolved",
            "government_payload": {},
            "created_at": created_at,
            "updated_at": created_at,
        }
        record["government_payload"] = build_government_payload(record, resolution)

        persisted = self._persist_to_supabase(record)
        if persisted:
            record.update(self._normalise_db_record(persisted))

        with self._lock:
            self._records[reference_id] = dict(record)

        self.append_timeline_event(
            reference_id=reference_id,
            event_type="complaint_registered",
            payload={
                "status": record["status"],
                "category": record["category"],
                "call_sid": record["call_sid"],
            },
        )
        self.append_timeline_event(
            reference_id=reference_id,
            event_type="government_payload_created",
            payload=record["government_payload"],
        )
        return dict(record)

    def append_timeline_event(
        self,
        *,
        reference_id: str,
        event_type: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Append a complaint timeline event locally and in Supabase when available."""

        if event_type not in COMPLAINT_TIMELINE_EVENT_TYPES:
            raise ValueError(f"Unknown complaint timeline event: {event_type}")

        event = {
            "id": str(uuid4()),
            "reference_id": reference_id,
            "event_type": event_type,
            "payload": payload or {},
            "created_at": _utc_now(),
        }
        with self._lock:
            self._timelines.setdefault(reference_id, []).append(dict(event))

        if self.settings.supabase_configured:
            try:
                db.insert_complaint_timeline_event(
                    reference_id=reference_id,
                    event_type=event_type,
                    payload=payload or {},
                )
            except Exception:
                pass
        return dict(event)

    def list_complaints(self, limit: int = 50, call_sid: str | None = None) -> list[dict[str, Any]]:
        """List complaints from local cache first, then Supabase."""

        with self._lock:
            records = list(self._records.values())
        if call_sid:
            records = [record for record in records if record.get("call_sid") == call_sid]
        if records:
            records.sort(key=lambda item: item.get("created_at", ""), reverse=True)
            return [dict(record) for record in records[:limit]]

        try:
            rows = db.get_complaints(limit=limit, call_sid=call_sid)
            return [self._normalise_db_record(row) for row in rows]
        except Exception:
            return []

    def get_by_reference(self, reference_id: str) -> dict[str, Any] | None:
        with self._lock:
            record = self._records.get(reference_id)
        if record:
            return dict(record)
        try:
            row = db.get_complaint_by_reference(reference_id)
            return self._normalise_db_record(row) if row else None
        except Exception:
            return None

    def get_by_call_sid(self, call_sid: str) -> dict[str, Any] | None:
        with self._lock:
            for record in self._records.values():
                if record.get("call_sid") == call_sid:
                    return dict(record)
        try:
            rows = db.get_complaints(limit=1, call_sid=call_sid)
            if rows:
                return self._normalise_db_record(rows[0])
        except Exception:
            pass
        return None

    def get_timeline(self, reference_id: str, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock:
            timeline = list(self._timelines.get(reference_id, []))
        if timeline:
            timeline.sort(key=lambda item: item.get("created_at", ""), reverse=True)
            return [dict(event) for event in timeline[:limit]]

        try:
            return db.get_complaint_timeline(reference_id=reference_id, limit=limit)
        except Exception:
            return []

    def _persist_to_supabase(self, record: dict[str, Any]) -> dict[str, Any]:
        if not self.settings.supabase_configured:
            return {}
        try:
            call_log = db.get_call_log(record["call_sid"]) or {}
            return db.register_complaint(
                call_log_id=call_log.get("id"),
                reference_id=record["reference_id"],
                call_sid=record["call_sid"],
                caller_number=record.get("caller_number") or call_log.get("caller_number") or "",
                category=record["category"],
                description=record["description"],
                location=record["location"],
                urgency=record["urgency"],
                language=record["language"],
                dialect=record["dialect"],
                transcript_ref=record["transcript_ref"],
                status=record["status"],
                assigned_agent=record["assigned_agent"],
                source=record["source"],
                government_payload=record["government_payload"],
            )
        except Exception:
            return {}

    @staticmethod
    def _normalise_db_record(row: dict[str, Any]) -> dict[str, Any]:
        record = dict(row or {})
        payload = record.get("government_payload")
        if isinstance(payload, str):
            import json

            try:
                record["government_payload"] = json.loads(payload)
            except Exception:
                record["government_payload"] = {}
        return record


complaint_registry = ComplaintRegistry()


def get_complaint_registry() -> ComplaintRegistry:
    return complaint_registry

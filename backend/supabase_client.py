"""
Sahayak 1092 – Supabase Client & Data Layer
============================================
Schema + helper functions for:
  • resolved_cases   – knowledge base of past human-resolved cases
  • agents           – list of available human agents with language skills
  • call_logs        – per-call transcript, summary, outcome
  • complaints       – registered complaints / actions
"""

import base64
import os
import json
import datetime as dt
from typing import Any, Optional
from uuid import uuid4
from dotenv import load_dotenv
from supabase import create_client, Client

from backend.intelligence.seed_cases import resolved_case_seed_data

load_dotenv()

SUPABASE_URL: str = ""
SUPABASE_KEY: str = ""
SUPABASE_KEY_SOURCE: str = "missing"

_client: Optional[Client] = None
_last_error: dict[str, str] | None = None


def _read_supabase_env() -> tuple[str, str, str]:
    load_dotenv()
    url = os.getenv("SUPABASE_URL", "").strip()
    candidates = (
        ("service_role", os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()),
        ("supabase_key", os.getenv("SUPABASE_KEY", "").strip()),
        ("anon", os.getenv("SUPABASE_ANON_KEY", "").strip()),
    )
    for source, key in candidates:
        if key:
            return url, key, source
    return url, "", "missing"


def _refresh_config_from_env() -> None:
    global SUPABASE_URL, SUPABASE_KEY, SUPABASE_KEY_SOURCE, _client
    url, key, source = _read_supabase_env()
    if (url, key, source) != (SUPABASE_URL, SUPABASE_KEY, SUPABASE_KEY_SOURCE):
        SUPABASE_URL = url
        SUPABASE_KEY = key
        SUPABASE_KEY_SOURCE = source
        _client = None


def _decode_jwt_role(key: str) -> str:
    parts = (key or "").split(".")
    if len(parts) < 2:
        return "unknown"
    try:
        payload = parts[1] + "=" * (-len(parts[1]) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload.encode("utf-8")))
        return str(data.get("role") or "unknown")
    except Exception:
        return "unknown"


def _json_value(value: Any) -> Any:
    return json.loads(json.dumps(value, default=str))


def _record_error(context: str, exc: Exception) -> None:
    global _last_error
    _last_error = {
        "context": context,
        "type": type(exc).__name__,
        "message": str(exc)[:500],
    }
    print(f"[WARN] Supabase {context} failed: {type(exc).__name__}: {str(exc)[:300]}")


def _clear_error() -> None:
    global _last_error
    _last_error = None


_refresh_config_from_env()


def get_client() -> Client:
    """Lazy-initialise and return the Supabase client."""
    global _client
    _refresh_config_from_env()
    if _client is None:
        if not SUPABASE_URL or not SUPABASE_KEY:
            raise RuntimeError("SUPABASE_URL / SUPABASE_KEY not set in .env")
        _client = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _client


def supabase_health(probe: bool = False) -> dict[str, Any]:
    """Return Supabase readiness and the last safe error, without exposing secrets."""

    _refresh_config_from_env()
    key_role = _decode_jwt_role(SUPABASE_KEY)
    status: dict[str, Any] = {
        "configured": bool(SUPABASE_URL and SUPABASE_KEY),
        "available": None,
        "key_source": SUPABASE_KEY_SOURCE,
        "key_role": key_role,
        "write_recommendation": "service_role" if key_role == "anon" else "ok",
    }
    if _last_error:
        status["last_error"] = dict(_last_error)
        status["available"] = False
    if not status["configured"]:
        status["available"] = False
        return status
    if key_role == "anon":
        status["warning"] = (
            "Anon keys cannot write to RLS-protected tables unless policies allow it. "
            "Use SUPABASE_SERVICE_ROLE_KEY on the backend for durable writes."
        )
    if not probe:
        return status
    try:
        get_client().table("call_logs").select("call_sid").limit(1).execute()
        _clear_error()
        status["available"] = True
    except Exception as exc:
        _record_error("health_probe", exc)
        status["available"] = False
        status["last_error"] = dict(_last_error or {})
    return status


def write_diagnostic_call_log(cleanup: bool = True) -> dict[str, Any]:
    """Probe whether the configured key can insert call_logs rows."""

    sid = f"diagnostic-{uuid4().hex[:12]}"
    sb = get_client()
    try:
        resp = sb.table("call_logs").insert(
            {
                "call_sid": sid,
                "caller_number": "+910000000000",
                "transcript": [],
                "ai_summary": "Supabase write diagnostic",
            },
        ).execute()
        if cleanup:
            sb.table("call_logs").delete().eq("call_sid", sid).execute()
        _clear_error()
        return {
            "ok": True,
            "call_sid": sid,
            "inserted": bool(resp.data),
            "cleaned_up": cleanup,
        }
    except Exception as exc:
        _record_error("write_diagnostic_call_log", exc)
        try:
            if cleanup:
                sb.table("call_logs").delete().eq("call_sid", sid).execute()
        except Exception:
            pass
        return {
            "ok": False,
            "call_sid": sid,
            "error": dict(_last_error or {}),
            "hint": (
                "If the error mentions row-level security, put the backend service-role key "
                "in SUPABASE_SERVICE_ROLE_KEY or add explicit insert policies."
            ),
        }


# ──────────────────────────────────────────────
# SQL to bootstrap tables (run once via Supabase SQL editor)
# ──────────────────────────────────────────────
BOOTSTRAP_SQL = """
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- 1. Resolved Cases – knowledge base for similarity matching
CREATE TABLE IF NOT EXISTS resolved_cases (
    id            UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    summary       TEXT NOT NULL,
    category      TEXT,           -- e.g. "theft", "accident", "domestic"
    language      TEXT,           -- e.g. "kannada", "hindi", "english"
    dialect       TEXT,
    urgency_band  TEXT DEFAULT 'medium',
    resolution    TEXT NOT NULL,  -- how it was resolved
    tags          TEXT[],
    embedding     VECTOR(1536),   -- pgvector embedding for similarity
    source_call_sid TEXT,
    created_at    TIMESTAMPTZ DEFAULT now(),
    updated_at    TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE IF EXISTS resolved_cases ADD COLUMN IF NOT EXISTS dialect TEXT;
ALTER TABLE IF EXISTS resolved_cases ADD COLUMN IF NOT EXISTS urgency_band TEXT DEFAULT 'medium';
ALTER TABLE IF EXISTS resolved_cases ADD COLUMN IF NOT EXISTS embedding VECTOR(1536);
ALTER TABLE IF EXISTS resolved_cases ADD COLUMN IF NOT EXISTS source_call_sid TEXT;
ALTER TABLE IF EXISTS resolved_cases ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT now();

-- 2. Agents
CREATE TABLE IF NOT EXISTS agents (
    id            UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    name          TEXT NOT NULL,
    badge_id      TEXT UNIQUE,
    phone         TEXT,
    languages     TEXT[],         -- ["kannada","hindi","english"]
    specialties   TEXT[],         -- ["domestic","cyber","traffic"]
    is_available  BOOLEAN DEFAULT true,
    current_load  INT DEFAULT 0,
    avg_wait_sec  INT DEFAULT 0,
    created_at    TIMESTAMPTZ DEFAULT now()
);

-- 3. Call Logs
CREATE TABLE IF NOT EXISTS call_logs (
    id            UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    call_sid      TEXT UNIQUE,
    caller_number TEXT,
    language      TEXT,
    dialect       TEXT,
    sentiment     TEXT,           -- "calm","anxious","distressed","angry"
    urgency       FLOAT DEFAULT 0.5, -- 0.0 to 1.0
    confidence    FLOAT DEFAULT 0.5,
    transcript    JSONB DEFAULT '[]'::jsonb,
    ai_summary    TEXT,
    outcome       TEXT,           -- "ai_resolved","handed_over","queued"
    agent_id      UUID REFERENCES agents(id),
    similar_case  UUID REFERENCES resolved_cases(id),
    similarity_score FLOAT,
    similarity_source TEXT,
    adapted_resolution TEXT,
    complaint_reference_id TEXT,
    handover_context JSONB DEFAULT '{}'::jsonb,
    routing_score_breakdown JSONB DEFAULT '{}'::jsonb,
    officer_first_sentence TEXT,
    transfer_status TEXT,
    transfer_mode TEXT,
    handover_accepted_by TEXT,
    handover_accepted_at TIMESTAMPTZ,
    queue_entry_id TEXT,
    queue_status TEXT,
    queue_position INT,
    queue_priority_score FLOAT,
    queue_estimated_wait_sec INT,
    queue_service_target TEXT,
    high_help_alert_at TIMESTAMPTZ,
    created_at    TIMESTAMPTZ DEFAULT now(),
    updated_at    TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE IF EXISTS call_logs ADD COLUMN IF NOT EXISTS similar_case UUID REFERENCES resolved_cases(id);
ALTER TABLE IF EXISTS call_logs ADD COLUMN IF NOT EXISTS similarity_score FLOAT;
ALTER TABLE IF EXISTS call_logs ADD COLUMN IF NOT EXISTS similarity_source TEXT;
ALTER TABLE IF EXISTS call_logs ADD COLUMN IF NOT EXISTS adapted_resolution TEXT;
ALTER TABLE IF EXISTS call_logs ADD COLUMN IF NOT EXISTS complaint_reference_id TEXT;
ALTER TABLE IF EXISTS call_logs ADD COLUMN IF NOT EXISTS handover_context JSONB DEFAULT '{}'::jsonb;
ALTER TABLE IF EXISTS call_logs ADD COLUMN IF NOT EXISTS routing_score_breakdown JSONB DEFAULT '{}'::jsonb;
ALTER TABLE IF EXISTS call_logs ADD COLUMN IF NOT EXISTS officer_first_sentence TEXT;
ALTER TABLE IF EXISTS call_logs ADD COLUMN IF NOT EXISTS transfer_status TEXT;
ALTER TABLE IF EXISTS call_logs ADD COLUMN IF NOT EXISTS transfer_mode TEXT;
ALTER TABLE IF EXISTS call_logs ADD COLUMN IF NOT EXISTS handover_accepted_by TEXT;
ALTER TABLE IF EXISTS call_logs ADD COLUMN IF NOT EXISTS handover_accepted_at TIMESTAMPTZ;
ALTER TABLE IF EXISTS call_logs ADD COLUMN IF NOT EXISTS queue_entry_id TEXT;
ALTER TABLE IF EXISTS call_logs ADD COLUMN IF NOT EXISTS queue_status TEXT;
ALTER TABLE IF EXISTS call_logs ADD COLUMN IF NOT EXISTS queue_position INT;
ALTER TABLE IF EXISTS call_logs ADD COLUMN IF NOT EXISTS queue_priority_score FLOAT;
ALTER TABLE IF EXISTS call_logs ADD COLUMN IF NOT EXISTS queue_estimated_wait_sec INT;
ALTER TABLE IF EXISTS call_logs ADD COLUMN IF NOT EXISTS queue_service_target TEXT;
ALTER TABLE IF EXISTS call_logs ADD COLUMN IF NOT EXISTS high_help_alert_at TIMESTAMPTZ;

-- 4. Complaints
CREATE TABLE IF NOT EXISTS complaints (
    id             UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    reference_id   TEXT UNIQUE,
    call_log_id    UUID REFERENCES call_logs(id),
    call_sid        TEXT,
    category       TEXT,
    description    TEXT,
    location       TEXT,
    urgency        FLOAT,
    language       TEXT,
    dialect        TEXT,
    transcript_ref TEXT,
    status         TEXT DEFAULT 'registered',  -- registered, in_progress, resolved
    assigned_agent UUID REFERENCES agents(id),
    source         TEXT DEFAULT 'ai_resolved',
    government_payload JSONB DEFAULT '{}'::jsonb,
    created_at     TIMESTAMPTZ DEFAULT now(),
    updated_at     TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE IF EXISTS complaints ADD COLUMN IF NOT EXISTS reference_id TEXT UNIQUE;
ALTER TABLE IF EXISTS complaints ADD COLUMN IF NOT EXISTS call_sid TEXT;
ALTER TABLE IF EXISTS complaints ADD COLUMN IF NOT EXISTS urgency FLOAT;
ALTER TABLE IF EXISTS complaints ADD COLUMN IF NOT EXISTS language TEXT;
ALTER TABLE IF EXISTS complaints ADD COLUMN IF NOT EXISTS dialect TEXT;
ALTER TABLE IF EXISTS complaints ADD COLUMN IF NOT EXISTS transcript_ref TEXT;
ALTER TABLE IF EXISTS complaints ADD COLUMN IF NOT EXISTS source TEXT DEFAULT 'ai_resolved';
ALTER TABLE IF EXISTS complaints ADD COLUMN IF NOT EXISTS government_payload JSONB DEFAULT '{}'::jsonb;
ALTER TABLE IF EXISTS complaints ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT now();

CREATE TABLE IF NOT EXISTS complaint_timeline (
    id            UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    reference_id  TEXT REFERENCES complaints(reference_id),
    event_type    TEXT NOT NULL,
    payload       JSONB DEFAULT '{}'::jsonb,
    created_at    TIMESTAMPTZ DEFAULT now()
);

-- 5. Call Queue – surge/priority queue entries
CREATE TABLE IF NOT EXISTS call_queue (
    id                 UUID PRIMARY KEY,
    call_sid           TEXT UNIQUE,
    caller_number      TEXT,
    language           TEXT,
    dialect            TEXT,
    category           TEXT,
    urgency            FLOAT,
    sentiment          TEXT,
    confidence         FLOAT,
    priority_score     FLOAT,
    status             TEXT DEFAULT 'waiting',
    reason             TEXT,
    position           INT DEFAULT 1,
    estimated_wait_sec INT DEFAULT 0,
    service_target     TEXT,
    dtmf_digit         TEXT,
    high_help_alert_at TIMESTAMPTZ,
    created_at         TIMESTAMPTZ DEFAULT now(),
    updated_at         TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE IF EXISTS call_queue ADD COLUMN IF NOT EXISTS caller_number TEXT;
ALTER TABLE IF EXISTS call_queue ADD COLUMN IF NOT EXISTS language TEXT;
ALTER TABLE IF EXISTS call_queue ADD COLUMN IF NOT EXISTS dialect TEXT;
ALTER TABLE IF EXISTS call_queue ADD COLUMN IF NOT EXISTS category TEXT;
ALTER TABLE IF EXISTS call_queue ADD COLUMN IF NOT EXISTS urgency FLOAT;
ALTER TABLE IF EXISTS call_queue ADD COLUMN IF NOT EXISTS sentiment TEXT;
ALTER TABLE IF EXISTS call_queue ADD COLUMN IF NOT EXISTS confidence FLOAT;
ALTER TABLE IF EXISTS call_queue ADD COLUMN IF NOT EXISTS priority_score FLOAT;
ALTER TABLE IF EXISTS call_queue ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'waiting';
ALTER TABLE IF EXISTS call_queue ADD COLUMN IF NOT EXISTS reason TEXT;
ALTER TABLE IF EXISTS call_queue ADD COLUMN IF NOT EXISTS position INT DEFAULT 1;
ALTER TABLE IF EXISTS call_queue ADD COLUMN IF NOT EXISTS estimated_wait_sec INT DEFAULT 0;
ALTER TABLE IF EXISTS call_queue ADD COLUMN IF NOT EXISTS service_target TEXT;
ALTER TABLE IF EXISTS call_queue ADD COLUMN IF NOT EXISTS dtmf_digit TEXT;
ALTER TABLE IF EXISTS call_queue ADD COLUMN IF NOT EXISTS high_help_alert_at TIMESTAMPTZ;
ALTER TABLE IF EXISTS call_queue ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT now();

-- 6. Call Events – immutable audit trail for every AI/routing decision
CREATE TABLE IF NOT EXISTS call_events (
    id          UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    call_sid    TEXT,
    event_type  TEXT NOT NULL,
    payload     JSONB DEFAULT '{}'::jsonb,
    phase       TEXT,
    language    TEXT,
    dialect     TEXT,
    urgency     FLOAT,
    confidence  FLOAT,
    created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_call_events_call_sid ON call_events(call_sid);
CREATE INDEX IF NOT EXISTS idx_call_events_type ON call_events(event_type);
CREATE INDEX IF NOT EXISTS idx_call_events_created_at ON call_events(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_complaints_reference_id ON complaints(reference_id);
CREATE INDEX IF NOT EXISTS idx_complaints_call_sid ON complaints(call_sid);
CREATE INDEX IF NOT EXISTS idx_complaints_status ON complaints(status);
CREATE INDEX IF NOT EXISTS idx_complaint_timeline_reference_id ON complaint_timeline(reference_id);
CREATE INDEX IF NOT EXISTS idx_call_queue_status_priority ON call_queue(status, priority_score DESC);
CREATE INDEX IF NOT EXISTS idx_call_queue_call_sid ON call_queue(call_sid);
CREATE INDEX IF NOT EXISTS idx_resolved_cases_category ON resolved_cases(category);
CREATE INDEX IF NOT EXISTS idx_resolved_cases_language ON resolved_cases(language);
CREATE INDEX IF NOT EXISTS idx_resolved_cases_urgency_band ON resolved_cases(urgency_band);
CREATE INDEX IF NOT EXISTS idx_resolved_cases_embedding
    ON resolved_cases USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

CREATE OR REPLACE FUNCTION match_resolved_cases(
    query_embedding VECTOR(1536),
    match_count INT DEFAULT 10,
    match_threshold FLOAT DEFAULT 0.15,
    filter_category TEXT DEFAULT NULL,
    filter_language TEXT DEFAULT NULL,
    filter_dialect TEXT DEFAULT NULL,
    filter_urgency_band TEXT DEFAULT NULL
)
RETURNS TABLE (
    id UUID,
    summary TEXT,
    category TEXT,
    language TEXT,
    dialect TEXT,
    urgency_band TEXT,
    resolution TEXT,
    tags TEXT[],
    source_call_sid TEXT,
    created_at TIMESTAMPTZ,
    similarity FLOAT
)
LANGUAGE plpgsql
STABLE
AS $$
BEGIN
    RETURN QUERY
    SELECT
        rc.id,
        rc.summary,
        rc.category,
        rc.language,
        rc.dialect,
        rc.urgency_band,
        rc.resolution,
        rc.tags,
        rc.source_call_sid,
        rc.created_at,
        (1 - (rc.embedding <=> query_embedding))::FLOAT AS similarity
    FROM resolved_cases rc
    WHERE rc.embedding IS NOT NULL
      AND (filter_category IS NULL OR rc.category = filter_category)
      AND (filter_language IS NULL OR rc.language = filter_language)
      AND (
          filter_dialect IS NULL
          OR filter_dialect = ''
          OR rc.dialect = filter_dialect
          OR rc.dialect IS NULL
          OR rc.dialect = ''
      )
      AND (filter_urgency_band IS NULL OR rc.urgency_band = filter_urgency_band)
      AND (1 - (rc.embedding <=> query_embedding)) >= match_threshold
    ORDER BY rc.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;

-- Enable Row Level Security (optional for hackathon)
-- ALTER TABLE resolved_cases ENABLE ROW LEVEL SECURITY;
"""


# ──────────────────────────────────────────────
# Resolved Cases (Knowledge Base)
# ──────────────────────────────────────────────

def _vector_literal(embedding: list[float]) -> str:
    """Return a pgvector-compatible literal for PostgREST RPC calls."""

    return "[" + ",".join(f"{float(value):.8f}" for value in embedding) + "]"


def search_similar_cases(summary: str, category: str = None, limit: int = 5) -> list[dict]:
    """
    Text-based similarity search against resolved cases.
    In production, use pgvector cosine similarity on embeddings.
    For hackathon, we use a simple text-match approach.
    """
    sb = get_client()
    query = sb.table("resolved_cases").select("*")
    if category:
        query = query.eq("category", category)
    query = query.ilike("summary", f"%{summary[:80]}%").limit(limit)
    try:
        resp = query.execute()
        _clear_error()
        return resp.data or []
    except Exception as exc:
        _record_error("search_similar_cases", exc)
        return []


def get_all_resolved_cases(limit: int = 100, include_embedding: bool = False) -> list[dict]:
    """Fetch all resolved cases for dashboard display."""
    sb = get_client()
    try:
        columns = "*" if include_embedding else (
            "id,summary,category,language,dialect,urgency_band,resolution,tags,"
            "source_call_sid,created_at,updated_at"
        )
        resp = sb.table("resolved_cases").select(columns).order(
            "created_at", desc=True
        ).limit(limit).execute()
        _clear_error()
        return resp.data or []
    except Exception as exc:
        _record_error("get_all_resolved_cases", exc)
        return []


def get_resolved_cases_missing_embeddings(limit: int = 100) -> list[dict]:
    """Fetch resolved cases that need vector embeddings backfilled."""
    sb = get_client()
    try:
        resp = sb.table("resolved_cases").select(
            "id,summary,category,language,dialect,urgency_band,resolution,tags,source_call_sid"
        ).is_("embedding", "null").order("created_at", desc=True).limit(limit).execute()
        _clear_error()
        return resp.data or []
    except Exception as exc:
        _record_error("get_resolved_cases_missing_embeddings", exc)
        return []


def update_resolved_case_embedding(case_id: str, embedding: list[float]) -> dict:
    """Update one resolved case with its generated embedding."""
    sb = get_client()
    try:
        resp = sb.table("resolved_cases").update({
            "embedding": embedding,
            "updated_at": dt.datetime.now(dt.UTC).isoformat(),
        }).eq("id", case_id).execute()
        _clear_error()
        return resp.data[0] if resp.data else {}
    except Exception as exc:
        _record_error("update_resolved_case_embedding", exc)
        return {}


def match_resolved_cases(
    query_embedding: list[float],
    category: str | None = None,
    language: str | None = None,
    dialect: str | None = None,
    urgency_band: str | None = None,
    limit: int = 10,
    threshold: float = 0.15,
    raise_errors: bool = False,
) -> list[dict]:
    """Run database-side pgvector top-k search through the Supabase RPC."""
    sb = get_client()
    params = {
        "query_embedding": _vector_literal(query_embedding),
        "match_count": limit,
        "match_threshold": threshold,
        "filter_category": category,
        "filter_language": language,
        "filter_dialect": dialect,
        "filter_urgency_band": urgency_band,
    }
    try:
        resp = sb.rpc("match_resolved_cases", params).execute()
        _clear_error()
        return resp.data or []
    except Exception as exc:
        _record_error("match_resolved_cases", exc)
        if raise_errors:
            raise
        return []


def vector_db_health(embedding_dimension: int = 1536, probe: bool = False) -> dict:
    """Return vector DB readiness metadata without forcing network calls by default."""
    _refresh_config_from_env()
    status = {
        "provider": "supabase_pgvector",
        "configured": bool(SUPABASE_URL and SUPABASE_KEY),
        "available": None,
        "rpc": "match_resolved_cases",
        "embedding_dimension": embedding_dimension,
    }
    if not status["configured"]:
        status["available"] = False
        return status
    if not probe:
        status["available"] = "not_probed"
        return status
    try:
        match_resolved_cases(
            query_embedding=[0.0] * embedding_dimension,
            limit=1,
            threshold=-1.0,
            raise_errors=True,
        )
        status["available"] = True
    except Exception as exc:
        status["available"] = False
        status["error"] = str(exc)
    return status


def insert_resolved_case(
    summary: str,
    category: str,
    language: str,
    resolution: str,
    tags: list[str] = None,
    dialect: str = "",
    urgency_band: str = "medium",
    source_call_sid: str | None = None,
    embedding: list[float] | None = None,
) -> dict:
    """Add a newly resolved case to the knowledge base."""
    sb = get_client()
    row = {
        "summary": summary,
        "category": category,
        "language": language,
        "dialect": dialect,
        "urgency_band": urgency_band,
        "resolution": resolution,
        "tags": tags or [],
        "source_call_sid": source_call_sid,
    }
    if embedding:
        row["embedding"] = embedding
    try:
        resp = sb.table("resolved_cases").insert(row).execute()
        _clear_error()
        return resp.data[0] if resp.data else {}
    except Exception as exc:
        _record_error("insert_resolved_case", exc)
        return {}


# ──────────────────────────────────────────────
# Agents
# ──────────────────────────────────────────────

def get_available_agents(language: str = None) -> list[dict]:
    """Get agents that are currently available, optionally filtered by language."""
    sb = get_client()
    query = sb.table("agents").select("*").eq("is_available", True)
    if language:
        query = query.contains("languages", [language])
    try:
        resp = query.order("current_load").execute()
        _clear_error()
        return resp.data or []
    except Exception as exc:
        _record_error("get_available_agents", exc)
        return []


def get_all_agents() -> list[dict]:
    """Fetch all agents for dashboard."""
    sb = get_client()
    try:
        resp = sb.table("agents").select("*").execute()
        _clear_error()
        return resp.data or []
    except Exception as exc:
        _record_error("get_all_agents", exc)
        return []


def get_agent_by_id(agent_id: str) -> Optional[dict]:
    """Fetch a single agent by ID."""
    sb = get_client()
    try:
        resp = sb.table("agents").select("*").eq("id", agent_id).single().execute()
        _clear_error()
        return resp.data
    except Exception as exc:
        _record_error("get_agent_by_id", exc)
        return None


def update_agent_availability(agent_id: str, available: bool) -> dict:
    """Toggle agent availability."""
    sb = get_client()
    try:
        resp = sb.table("agents").update({
            "is_available": available
        }).eq("id", agent_id).execute()
        _clear_error()
        return resp.data[0] if resp.data else {}
    except Exception as exc:
        _record_error("update_agent_availability", exc)
        return {}


def increment_agent_load(agent_id: str) -> None:
    """Increment agent's current call load."""
    sb = get_client()
    try:
        # Fetch current load, then increment
        agent = sb.table("agents").select("current_load").eq("id", agent_id).execute()
        if agent.data:
            new_load = (agent.data[0].get("current_load", 0)) + 1
            sb.table("agents").update({"current_load": new_load}).eq("id", agent_id).execute()
        _clear_error()
    except Exception as exc:
        _record_error("increment_agent_load", exc)


# ──────────────────────────────────────────────
# Call Logs
# ──────────────────────────────────────────────

def create_call_log(call_sid: str, caller_number: str) -> dict:
    """Create a new call log entry when a call comes in."""
    sb = get_client()
    row = {
        "call_sid": call_sid,
        "caller_number": caller_number,
        "transcript": [],
    }
    try:
        resp = sb.table("call_logs").upsert(row, on_conflict="call_sid").execute()
        _clear_error()
        return resp.data[0] if resp.data else {}
    except Exception as exc:
        _record_error("create_call_log", exc)
        return {}


def update_call_log(call_sid: str, **fields) -> dict:
    """Update a call log with analysis results, transcript, etc."""
    sb = get_client()
    fields["updated_at"] = dt.datetime.now(dt.UTC).isoformat()
    if "transcript" in fields and isinstance(fields["transcript"], list):
        fields["transcript"] = _json_value(fields["transcript"])
    for json_field in ("handover_context", "routing_score_breakdown"):
        if json_field in fields and isinstance(fields[json_field], (dict, list)):
            fields[json_field] = _json_value(fields[json_field])
    try:
        row = {"call_sid": call_sid, **fields}
        resp = sb.table("call_logs").upsert(row, on_conflict="call_sid").execute()
        _clear_error()
        return resp.data[0] if resp.data else {}
    except Exception as exc:
        _record_error("update_call_log", exc)
        return {}


def insert_call_event(event: dict) -> dict:
    """Insert an immutable audit event for a call."""
    sb = get_client()
    row = {
        "call_sid": event.get("call_sid"),
        "event_type": event.get("event_type"),
        "payload": _json_value(event.get("payload", {})),
        "phase": event.get("phase"),
        "language": event.get("language"),
        "dialect": event.get("dialect"),
        "urgency": event.get("urgency"),
        "confidence": event.get("confidence"),
        "created_at": event.get("created_at"),
    }
    try:
        resp = sb.table("call_events").insert(row).execute()
        _clear_error()
        return resp.data[0] if resp.data else {}
    except Exception as exc:
        _record_error("insert_call_event", exc)
        return {}


def get_call_events(call_sid: str = None, limit: int = 100) -> list[dict]:
    """Fetch audit events, optionally filtered by call SID."""
    sb = get_client()
    try:
        query = sb.table("call_events").select("*")
        if call_sid:
            query = query.eq("call_sid", call_sid)
        resp = query.order("created_at", desc=True).limit(limit).execute()
        _clear_error()
        return resp.data or []
    except Exception as exc:
        _record_error("get_call_events", exc)
        return []


def get_call_log(call_sid: str) -> Optional[dict]:
    """Retrieve a single call log by SID."""
    sb = get_client()
    try:
        resp = sb.table("call_logs").select("*").eq("call_sid", call_sid).single().execute()
        _clear_error()
        return resp.data
    except Exception as exc:
        _record_error("get_call_log", exc)
        return None


def get_recent_calls(limit: int = 50) -> list[dict]:
    """Fetch recent call logs for the dashboard."""
    sb = get_client()
    try:
        resp = sb.table("call_logs").select("*").order(
            "created_at", desc=True
        ).limit(limit).execute()
        _clear_error()
        return resp.data or []
    except Exception as exc:
        _record_error("get_recent_calls", exc)
        return []


def get_active_calls() -> list[dict]:
    """Fetch calls that are currently active (no outcome yet)."""
    sb = get_client()
    try:
        resp = sb.table("call_logs").select("*").is_("outcome", "null").order(
            "created_at", desc=True
        ).execute()
        _clear_error()
        return resp.data or []
    except Exception as exc:
        _record_error("get_active_calls", exc)
        return []


# ──────────────────────────────────────────────
# Call Queue
# ──────────────────────────────────────────────

def upsert_queue_entry(entry: dict) -> dict:
    """Insert/update one priority queue entry."""
    sb = get_client()
    row = dict(entry)
    try:
        resp = sb.table("call_queue").upsert(row, on_conflict="call_sid").execute()
        _clear_error()
        return resp.data[0] if resp.data else {}
    except Exception as exc:
        _record_error("upsert_queue_entry", exc)
        return {}


def get_queue_entry(call_sid: str) -> Optional[dict]:
    """Fetch one queue entry by call SID."""
    sb = get_client()
    try:
        resp = sb.table("call_queue").select("*").eq("call_sid", call_sid).single().execute()
        _clear_error()
        return resp.data
    except Exception as exc:
        _record_error("get_queue_entry", exc)
        return None


def get_queue_entries(limit: int = 50, include_inactive: bool = True) -> list[dict]:
    """Fetch queue entries for dashboard/API."""
    sb = get_client()
    try:
        query = sb.table("call_queue").select("*")
        if not include_inactive:
            query = query.eq("status", "waiting")
        resp = query.order("priority_score", desc=True).order("created_at").limit(limit).execute()
        _clear_error()
        return resp.data or []
    except Exception as exc:
        _record_error("get_queue_entries", exc)
        return []


# ──────────────────────────────────────────────
# Complaints
# ──────────────────────────────────────────────

def register_complaint(
    call_log_id: str | None,
    category: str,
    description: str,
    location: str = None,
    *,
    reference_id: str | None = None,
    call_sid: str | None = None,
    urgency: float | None = None,
    language: str | None = None,
    dialect: str | None = None,
    transcript_ref: str | None = None,
    status: str = "registered",
    assigned_agent: str | None = None,
    source: str = "ai_resolved",
    government_payload: dict | None = None,
) -> dict:
    """Register a structured complaint/action linked to a call."""
    sb = get_client()
    row = {
        "call_log_id": call_log_id,
        "reference_id": reference_id,
        "call_sid": call_sid,
        "category": category,
        "description": description,
        "location": location,
        "urgency": urgency,
        "language": language,
        "dialect": dialect,
        "transcript_ref": transcript_ref,
        "status": status,
        "assigned_agent": assigned_agent,
        "source": source,
        "government_payload": _json_value(government_payload or {}),
        "updated_at": dt.datetime.now(dt.UTC).isoformat(),
    }
    row = {key: value for key, value in row.items() if value is not None}
    try:
        resp = sb.table("complaints").insert(row).execute()
        _clear_error()
        return resp.data[0] if resp.data else {}
    except Exception as exc:
        _record_error("register_complaint", exc)
        return {}


def get_complaints(limit: int = 50, call_sid: str | None = None) -> list[dict]:
    """Fetch recent complaints for dashboard."""
    sb = get_client()
    try:
        query = sb.table("complaints").select("*")
        if call_sid:
            query = query.eq("call_sid", call_sid)
        resp = query.order("created_at", desc=True).limit(limit).execute()
        _clear_error()
        return resp.data or []
    except Exception as exc:
        _record_error("get_complaints", exc)
        return []


def get_complaint_by_reference(reference_id: str) -> Optional[dict]:
    """Fetch one complaint by citizen-facing reference ID."""
    sb = get_client()
    try:
        resp = sb.table("complaints").select("*").eq("reference_id", reference_id).single().execute()
        _clear_error()
        return resp.data
    except Exception as exc:
        _record_error("get_complaint_by_reference", exc)
        return None


def insert_complaint_timeline_event(
    reference_id: str,
    event_type: str,
    payload: dict | None = None,
) -> dict:
    """Insert one complaint timeline event."""
    sb = get_client()
    row = {
        "reference_id": reference_id,
        "event_type": event_type,
        "payload": _json_value(payload or {}),
    }
    try:
        resp = sb.table("complaint_timeline").insert(row).execute()
        _clear_error()
        return resp.data[0] if resp.data else {}
    except Exception as exc:
        _record_error("insert_complaint_timeline_event", exc)
        return {}


def get_complaint_timeline(reference_id: str, limit: int = 100) -> list[dict]:
    """Fetch complaint timeline events by reference ID."""
    sb = get_client()
    try:
        resp = sb.table("complaint_timeline").select("*").eq(
            "reference_id",
            reference_id,
        ).order("created_at", desc=True).limit(limit).execute()
        _clear_error()
        return resp.data or []
    except Exception as exc:
        _record_error("get_complaint_timeline", exc)
        return []


# ──────────────────────────────────────────────
# Seed Data (for demo)
# ──────────────────────────────────────────────

SEED_AGENTS = [
    {
        "name": "Inspector Ravi Kumar",
        "badge_id": "KA-1092-001",
        "phone": "+919876543210",
        "languages": ["kannada", "hindi", "english"],
        "specialties": ["domestic", "theft"],
        "is_available": True,
        "current_load": 0,
        "avg_wait_sec": 15,
    },
    {
        "name": "SI Meena Kumari",
        "badge_id": "KA-1092-002",
        "phone": "+919876543211",
        "languages": ["kannada", "english"],
        "specialties": ["cyber", "fraud"],
        "is_available": True,
        "current_load": 1,
        "avg_wait_sec": 30,
    },
    {
        "name": "ASI Pradeep Singh",
        "badge_id": "KA-1092-003",
        "phone": "+919876543212",
        "languages": ["hindi", "english"],
        "specialties": ["traffic", "accident"],
        "is_available": True,
        "current_load": 0,
        "avg_wait_sec": 10,
    },
    {
        "name": "Constable Fatima Begum",
        "badge_id": "KA-1092-004",
        "phone": "+919876543213",
        "languages": ["kannada", "hindi", "urdu"],
        "specialties": ["domestic", "missing_person"],
        "is_available": False,
        "current_load": 3,
        "avg_wait_sec": 60,
    },
]

SEED_RESOLVED_CASES = resolved_case_seed_data()


async def seed_demo_data():
    """Insert demo agents and resolved cases if tables are empty."""
    sb = get_client()
    try:
        # Check if agents exist
        agents = sb.table("agents").select("id").limit(1).execute()
        if not agents.data:
            for agent in SEED_AGENTS:
                sb.table("agents").insert(agent).execute()
            print("✅ Seeded demo agents")

        # Check if resolved cases exist
        cases = sb.table("resolved_cases").select("id").limit(1).execute()
        if not cases.data:
            from backend.intelligence.similarity import generate_seed_case_embeddings

            resolved_cases = await generate_seed_case_embeddings()
            for case in resolved_cases:
                case.pop("id", None)
                sb.table("resolved_cases").insert(case).execute()
            print("✅ Seeded demo resolved cases")
    except Exception as e:
        print(f"⚠️  Seed skipped (tables may not exist yet): {e}")
        print("   Run the SQL from BOOTSTRAP_SQL in Supabase SQL Editor first.")

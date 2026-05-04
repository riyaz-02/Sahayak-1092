"""
Sahayak 1092 – Supabase Client & Data Layer
============================================
Schema + helper functions for:
  • resolved_cases   – knowledge base of past human-resolved cases
  • agents           – list of available human agents with language skills
  • call_logs        – per-call transcript, summary, outcome
  • complaints       – registered complaints / actions
"""

import os
import json
import datetime as dt
from typing import Optional
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY: str = os.getenv("SUPABASE_KEY", "")

_client: Optional[Client] = None


def get_client() -> Client:
    """Lazy-initialise and return the Supabase client."""
    global _client
    if _client is None:
        if not SUPABASE_URL or not SUPABASE_KEY:
            raise RuntimeError("SUPABASE_URL / SUPABASE_KEY not set in .env")
        _client = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _client


# ──────────────────────────────────────────────
# SQL to bootstrap tables (run once via Supabase SQL editor)
# ──────────────────────────────────────────────
BOOTSTRAP_SQL = """
-- 1. Resolved Cases – knowledge base for similarity matching
CREATE TABLE IF NOT EXISTS resolved_cases (
    id            UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    summary       TEXT NOT NULL,
    category      TEXT,           -- e.g. "theft", "accident", "domestic"
    language      TEXT,           -- e.g. "kannada", "hindi", "english"
    dialect       TEXT,
    resolution    TEXT NOT NULL,  -- how it was resolved
    tags          TEXT[],
    embedding     VECTOR(1536),   -- OpenAI ada-002 embedding for similarity
    created_at    TIMESTAMPTZ DEFAULT now()
);

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
    created_at    TIMESTAMPTZ DEFAULT now(),
    updated_at    TIMESTAMPTZ DEFAULT now()
);

-- 4. Complaints
CREATE TABLE IF NOT EXISTS complaints (
    id             UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    call_log_id    UUID REFERENCES call_logs(id),
    category       TEXT,
    description    TEXT,
    location       TEXT,
    status         TEXT DEFAULT 'registered',  -- registered, in_progress, resolved
    assigned_agent UUID REFERENCES agents(id),
    created_at     TIMESTAMPTZ DEFAULT now()
);

-- Enable Row Level Security (optional for hackathon)
-- ALTER TABLE resolved_cases ENABLE ROW LEVEL SECURITY;
"""


# ──────────────────────────────────────────────
# Resolved Cases (Knowledge Base)
# ──────────────────────────────────────────────

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
        return resp.data or []
    except Exception:
        return []


def get_all_resolved_cases(limit: int = 100) -> list[dict]:
    """Fetch all resolved cases for dashboard display."""
    sb = get_client()
    try:
        resp = sb.table("resolved_cases").select("*").order(
            "created_at", desc=True
        ).limit(limit).execute()
        return resp.data or []
    except Exception:
        return []


def insert_resolved_case(summary: str, category: str, language: str,
                         resolution: str, tags: list[str] = None) -> dict:
    """Add a newly resolved case to the knowledge base."""
    sb = get_client()
    row = {
        "summary": summary,
        "category": category,
        "language": language,
        "resolution": resolution,
        "tags": tags or [],
    }
    resp = sb.table("resolved_cases").insert(row).execute()
    return resp.data[0] if resp.data else {}


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
        return resp.data or []
    except Exception:
        return []


def get_all_agents() -> list[dict]:
    """Fetch all agents for dashboard."""
    sb = get_client()
    try:
        resp = sb.table("agents").select("*").execute()
        return resp.data or []
    except Exception:
        return []


def update_agent_availability(agent_id: str, available: bool) -> dict:
    """Toggle agent availability."""
    sb = get_client()
    resp = sb.table("agents").update({
        "is_available": available
    }).eq("id", agent_id).execute()
    return resp.data[0] if resp.data else {}


def increment_agent_load(agent_id: str) -> None:
    """Increment agent's current call load."""
    sb = get_client()
    # Fetch current load, then increment
    agent = sb.table("agents").select("current_load").eq("id", agent_id).execute()
    if agent.data:
        new_load = (agent.data[0].get("current_load", 0)) + 1
        sb.table("agents").update({"current_load": new_load}).eq("id", agent_id).execute()


# ──────────────────────────────────────────────
# Call Logs
# ──────────────────────────────────────────────

def create_call_log(call_sid: str, caller_number: str) -> dict:
    """Create a new call log entry when a call comes in."""
    sb = get_client()
    row = {
        "call_sid": call_sid,
        "caller_number": caller_number,
        "transcript": json.dumps([]),
    }
    try:
        resp = sb.table("call_logs").insert(row).execute()
        return resp.data[0] if resp.data else {}
    except Exception:
        return {"call_sid": call_sid}


def update_call_log(call_sid: str, **fields) -> dict:
    """Update a call log with analysis results, transcript, etc."""
    sb = get_client()
    fields["updated_at"] = dt.datetime.utcnow().isoformat()
    if "transcript" in fields and isinstance(fields["transcript"], list):
        fields["transcript"] = json.dumps(fields["transcript"])
    try:
        resp = sb.table("call_logs").update(fields).eq("call_sid", call_sid).execute()
        return resp.data[0] if resp.data else {}
    except Exception:
        return {}


def get_call_log(call_sid: str) -> Optional[dict]:
    """Retrieve a single call log by SID."""
    sb = get_client()
    try:
        resp = sb.table("call_logs").select("*").eq("call_sid", call_sid).single().execute()
        return resp.data
    except Exception:
        return None


def get_recent_calls(limit: int = 50) -> list[dict]:
    """Fetch recent call logs for the dashboard."""
    sb = get_client()
    try:
        resp = sb.table("call_logs").select("*").order(
            "created_at", desc=True
        ).limit(limit).execute()
        return resp.data or []
    except Exception:
        return []


def get_active_calls() -> list[dict]:
    """Fetch calls that are currently active (no outcome yet)."""
    sb = get_client()
    try:
        resp = sb.table("call_logs").select("*").is_("outcome", "null").order(
            "created_at", desc=True
        ).execute()
        return resp.data or []
    except Exception:
        return []


# ──────────────────────────────────────────────
# Complaints
# ──────────────────────────────────────────────

def register_complaint(call_log_id: str, category: str, description: str,
                       location: str = None) -> dict:
    """Register a complaint linked to a call."""
    sb = get_client()
    row = {
        "call_log_id": call_log_id,
        "category": category,
        "description": description,
        "location": location,
        "status": "registered",
    }
    try:
        resp = sb.table("complaints").insert(row).execute()
        return resp.data[0] if resp.data else {}
    except Exception:
        return {}


def get_complaints(limit: int = 50) -> list[dict]:
    """Fetch recent complaints for dashboard."""
    sb = get_client()
    try:
        resp = sb.table("complaints").select("*").order(
            "created_at", desc=True
        ).limit(limit).execute()
        return resp.data or []
    except Exception:
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

SEED_RESOLVED_CASES = [
    {
        "summary": "Caller reported mobile phone theft at Majestic bus stand. Stolen while boarding BMTC bus.",
        "category": "theft",
        "language": "kannada",
        "resolution": "FIR registered online. Advised to block SIM via telecom provider. Shared nearest police station details. Phone tracked via IMEI within 48 hours.",
        "tags": ["mobile_theft", "public_transport", "bangalore"],
    },
    {
        "summary": "Woman reported domestic violence by husband. Afraid for safety of children.",
        "category": "domestic",
        "language": "kannada",
        "resolution": "Immediate dispatch of nearest PCR van. Connected with Women Helpline 181. Temporary shelter arranged. FIR registered under IPC 498A.",
        "tags": ["domestic_violence", "women_safety", "urgent"],
    },
    {
        "summary": "Road accident reported on NH-44 near Tumkur toll. Two-wheeler hit by truck. Rider injured.",
        "category": "accident",
        "language": "hindi",
        "resolution": "Ambulance dispatched (108). Nearest hospital (Sri Siddhartha) alerted. Traffic police diverted traffic. FIR registered against truck driver.",
        "tags": ["road_accident", "highway", "medical_emergency"],
    },
    {
        "summary": "Neighbour playing loud music late at night causing disturbance. Repeated complaints ignored.",
        "category": "noise",
        "language": "english",
        "resolution": "Local beat constable dispatched to address the issue. Warning issued under Noise Pollution Rules. Follow-up scheduled for next 3 days.",
        "tags": ["noise_complaint", "neighbourhood", "non_urgent"],
    },
    {
        "summary": "Suspicious person loitering near school premises during school hours. Parents concerned.",
        "category": "suspicious_activity",
        "language": "kannada",
        "resolution": "PCR van dispatched for verification. Person identified and warned. School principal informed. Increased patrol scheduled near school.",
        "tags": ["suspicious_activity", "school_safety", "patrol"],
    },
]


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
            for case in SEED_RESOLVED_CASES:
                sb.table("resolved_cases").insert(case).execute()
            print("✅ Seeded demo resolved cases")
    except Exception as e:
        print(f"⚠️  Seed skipped (tables may not exist yet): {e}")
        print("   Run the SQL from BOOTSTRAP_SQL in Supabase SQL Editor first.")

-- Sahayak 1092 database schema
-- Keep this file in sync with `BOOTSTRAP_SQL` in backend/supabase_client.py.

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS resolved_cases (
    id            UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    summary       TEXT NOT NULL,
    category      TEXT,
    language      TEXT,
    dialect       TEXT,
    urgency_band  TEXT DEFAULT 'medium',
    resolution    TEXT NOT NULL,
    tags          TEXT[],
    embedding     VECTOR(1536),
    source_call_sid TEXT,
    created_at    TIMESTAMPTZ DEFAULT now(),
    updated_at    TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE IF EXISTS resolved_cases ADD COLUMN IF NOT EXISTS dialect TEXT;
ALTER TABLE IF EXISTS resolved_cases ADD COLUMN IF NOT EXISTS urgency_band TEXT DEFAULT 'medium';
ALTER TABLE IF EXISTS resolved_cases ADD COLUMN IF NOT EXISTS embedding VECTOR(1536);
ALTER TABLE IF EXISTS resolved_cases ADD COLUMN IF NOT EXISTS source_call_sid TEXT;
ALTER TABLE IF EXISTS resolved_cases ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT now();

CREATE TABLE IF NOT EXISTS agents (
    id            UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    name          TEXT NOT NULL,
    badge_id      TEXT UNIQUE,
    phone         TEXT,
    languages     TEXT[],
    specialties   TEXT[],
    is_available  BOOLEAN DEFAULT true,
    current_load  INT DEFAULT 0,
    avg_wait_sec  INT DEFAULT 0,
    created_at    TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS call_logs (
    id            UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    call_sid      TEXT UNIQUE,
    caller_number TEXT,
    language      TEXT,
    dialect       TEXT,
    sentiment     TEXT,
    urgency       FLOAT DEFAULT 0.5,
    confidence    FLOAT DEFAULT 0.5,
    transcript    JSONB DEFAULT '[]'::jsonb,
    ai_summary    TEXT,
    outcome       TEXT,
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
    status         TEXT DEFAULT 'registered',
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

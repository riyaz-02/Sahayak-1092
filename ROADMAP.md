# Sahayak 1092 Production Roadmap

This roadmap breaks the full Sahayak 1092 build into controlled phases. Each
phase should be completed, tested, and committed before moving to the next one.
The goal is to keep the project production-minded while still easy to run for
local development and competition demos.

## Build Principle

Sahayak 1092 must feel like a complete emergency voice operating system:

- AI-first for routine and high-confidence cases.
- Human-assisted only for true exceptions.
- Auditable at every decision point.
- Easy to run locally for demo and development.
- Structured enough to evolve into production deployment.

## Phase 0: Project Stabilization

### Goal

Make the current prototype reliably runnable before changing architecture.

### Tasks

- [x] Restore `requirements.txt`.
- [x] Expand `.env.example` with all required and optional settings.
- [x] Add `Makefile` or scripts for common commands.
- [x] Add `pytest`, `ruff`, and basic test configuration.
- [x] Add `.gitignore` coverage for local caches, logs, virtualenvs, and test output.
- [x] Verify backend imports cleanly.
- [x] Verify dashboard imports cleanly.

### Acceptance Criteria

- [x] `python -m backend.main` starts without import errors.
- [x] `streamlit run dashboard/app.py` starts without import errors.
- [x] `pytest` runs, even if only basic smoke tests exist.
- [x] No required local secrets are committed.

### Phase 0 Verification

- [x] `.venv/bin/python -m pip install --prefer-binary -r requirements.txt`
- [x] `.venv/bin/python -m compileall backend dashboard tests`
- [x] `.venv/bin/python -m pytest`
- [x] `.venv/bin/python -m ruff check backend dashboard tests`
- [x] `timeout 8s .venv/bin/python -m backend.main`
- [x] `timeout 10s .venv/bin/python -m streamlit run dashboard/app.py --server.headless true --server.port 8599`
- [x] `make PYTHON=.venv/bin/python smoke`

### Notes

This phase should not rewrite the system. It only makes the existing base safe
to work on.

## Phase 1: Modular Production Structure

### Goal

Introduce a clean backend structure without breaking existing endpoints.

### Target Structure

```text
backend/
  app.py
  config.py
  api/
    twilio.py
    dashboard.py
    health.py
  intelligence/
    analyzer.py
    resolver.py
    safety_rules.py
    schemas.py
    similarity.py
  persistence/
    repository.py
    pii.py
    models.sql
  routing/
    officer_router.py
    queue_manager.py
    transfer_service.py
  voice/
    audio_codec.py
    vad.py
    stt.py
    tts.py
    stream_handler.py
  tests/
```

Some files in the target structure are created in later phases when their
behavior is implemented. For example, production voice provider implementations
belong to Phase 7, complaint/action services belong to Phase 8, and transfer or
queue services belong to Phases 9-10. Phase 1 only establishes the modular
shape and compatibility wrappers.

### Tasks

- [x] Add `backend/config.py` for typed settings.
- [x] Add shared schemas in `backend/intelligence/schemas.py`.
- [x] Move rule logic into `backend/intelligence/safety_rules.py`.
- [x] Move officer scoring into `backend/routing/officer_router.py`.
- [x] Move audio conversion into `backend/voice/audio_codec.py`.
- [x] Keep compatibility wrappers for existing `backend/main.py`,
      `backend/decision_engine.py`, and `backend/media_stream.py`.

### Acceptance Criteria

- [x] Old endpoints remain in `backend/main.py` with the same paths.
- [x] Existing dashboard API contract is preserved.
- [x] Core logic can be imported from modular files.
- [x] No large behavior changes yet.

### Phase 1 Verification

- [x] `python -m compileall backend`
- [x] Modular import smoke check for config, schemas, safety rules, routing, and audio codec.
- [x] Full `backend.app:app` import verified after installing dependencies.

## Phase 2: Durable State and Audit Events

### Goal

Replace fragile in-memory-only call state with a durable state and event model.

### Tasks

- [x] Add `call_events` table to SQL schema.
- [x] Add repository methods:
  - [x] create call state
  - [x] update call state
  - [x] append call event
  - [x] fetch active calls
  - [x] fetch call transcript
- [x] Add optional Redis-backed live state.
- [x] Keep in-memory fallback for local development when Redis is unavailable.
- [x] Log important events:
  - [x] `call_started`
  - [x] `greeting_sent`
  - [x] `utterance_received`
  - [x] `stt_completed`
  - [x] `analysis_completed`
  - [x] `similarity_match_found`
  - [x] `vachan_requested`
  - [x] `vachan_confirmed`
  - [x] `vachan_rejected`
  - [x] `vachan_partial`
  - [x] `vachan_correction_requested`
  - [x] `complaint_registered`
  - [x] `handover_requested`
  - [x] `officer_matched`
  - [x] `queued`
  - [x] `dtmf_redirect`
  - [x] `high_help_alert`
  - [x] `call_completed`

### Acceptance Criteria

- [x] A test pipeline call creates a call record.
- [x] Each pipeline step creates audit events.
- [x] Active calls survive code paths without depending only on global memory.
- [x] Local development still works without Supabase or Redis by using fallback storage.

### Phase 2 Verification

- [x] `.venv/bin/python -m compileall backend dashboard tests`
- [x] `.venv/bin/python -m pytest`
- [x] `.venv/bin/python -m ruff check backend dashboard tests`
- [x] `make PYTHON=.venv/bin/python smoke`
- [x] `.venv/bin/python -c "from backend.app import app; print(app.title)"`
- [x] `timeout 8s .venv/bin/python -m backend.main`

## Phase 3: Structured Decision Engine

### Goal

Make AI analysis predictable, schema-based, and auditable.

### Tasks

- [x] Define strict `CallAnalysis` schema.
- [x] Define `DecisionResult` schema.
- [x] Add deterministic fallback analyzer for development and tests.
- [x] Add LLM analyzer with structured output when API key is configured.
- [x] Add confidence and urgency thresholds to settings.
- [x] Add rule engine for the three handover conditions:
  - [x] caller explicitly requests human
  - [x] urgency/distress is extreme
  - [x] low confidence after two attempts
- [x] Add unit tests for all decision paths.

### Acceptance Criteria

- [x] Test input in Kannada/Hindi/English returns structured analysis.
- [x] Low confidence requires two failed attempts before handover.
- [x] Human request triggers handover immediately.
- [x] Extreme urgency triggers handover immediately.
- [x] Normal confident issue enters Vachan before final action.

### Phase 3 Verification

- [x] `.venv/bin/python -m compileall backend dashboard tests`
- [x] `.venv/bin/python -m pytest`
- [x] `.venv/bin/python -m ruff check backend dashboard tests`
- [x] `make PYTHON=.venv/bin/python smoke`
- [x] `.venv/bin/python -c "from backend.app import app; print(app.title)"`
- [x] `timeout 8s .venv/bin/python -m backend.main`

## Phase 4: Smart Similarity Knowledge Base

### Goal

Make Smart Similarity Detection a real technical differentiator.

### Vector DB Role

The vector database stores embeddings for every human-resolved or AI-confirmed
case in `resolved_cases.embedding`. During a new call, Sahayak embeds the
current issue summary plus key metadata, retrieves the closest resolved cases,
filters/ranks them with category, language, dialect, and urgency band, then asks
the LLM only to adapt the selected resolution. The LLM must not search the whole
case history by itself.

Local development keeps a deterministic embedding fallback. Production should
use Supabase Postgres with pgvector for database-side top-k retrieval.

### Tasks

- [x] Add pgvector-ready SQL schema.
- [x] Add embedding provider abstraction.
- [x] Add local deterministic embedding fallback for tests and offline demo.
- [x] Generate embeddings for seeded resolved cases.
- [x] Query similar cases using:
  - [x] category
  - [x] language
  - [x] dialect when available
  - [x] urgency band
  - [x] vector similarity
- [x] Use LLM only to adapt retrieved resolution, not to search all cases.
- [x] Store `matched_case_id`, `similarity_score`, and `adapted_resolution`.

### Acceptance Criteria

- [x] Mobile theft scenario matches the seeded mobile theft case.
- [x] Similarity score is visible in API response.
- [x] Similarity match appears in dashboard.
- [x] Confirmed AI resolution adds a new resolved case.

### Phase 4 Verification

- [x] `.venv/bin/python -m compileall backend dashboard tests`
- [x] `.venv/bin/python -m pytest`
- [x] `.venv/bin/python -m ruff check backend dashboard tests`
- [x] `make PYTHON=.venv/bin/python smoke`
- [x] `.venv/bin/python -c "from backend.app import app; print(app.title)"`
- [x] `timeout 8s .venv/bin/python -m backend.main`

## Phase 5: Vachan Confirmation Loop

### Goal

Make citizen confirmation explicit, respectful, and stateful.

### Tasks

- [x] Add clear call phases:
  - [x] `collecting_issue`
  - [x] `clarifying`
  - [x] `vachan_pending`
  - [x] `vachan_partial`
  - [x] `resolved`
  - [x] `handover_pending`
  - [x] `queued`
- [x] Detect yes/no/partial confirmation.
- [x] If yes, register action.
- [x] If no, ask what was wrong.
- [x] If partial, ask only for the missing or incorrect field.
- [x] Log all Vachan decisions.

### Acceptance Criteria

- [x] AI never registers final complaint before confirmation.
- [x] "Yes" resolves and registers complaint.
- [x] "No" returns to correction flow.
- [x] Partial confirmation asks a targeted follow-up.

### Phase 5 Verification

- [x] `.venv/bin/python -m compileall backend dashboard tests`
- [x] `.venv/bin/python -m pytest`
- [x] `.venv/bin/python -m ruff check backend dashboard tests`
- [x] `make PYTHON=.venv/bin/python smoke`
- [x] `.venv/bin/python -c "from backend.app import app; print(app.title)"`
- [x] `timeout 8s .venv/bin/python -m backend.main`

### Checkpoint Through Phase 5

- [x] Core backend imports and app startup are stable.
- [x] Modular structure exists for config, API placeholders, intelligence,
      persistence, routing, and voice boundaries.
- [x] Text-mode decision flow works without paid ML provider keys.
- [x] Durable local fallback exists when Supabase or Redis is unavailable.
- [x] Audit events cover call state, analysis, similarity, Vachan, routing,
      queue, IVR, alert, and completion milestones.
- [x] Smart Similarity has deterministic/vector-style local retrieval and
      pgvector-ready schema.
- [x] Vachan confirmation prevents final complaint/action registration before
      citizen confirmation.

Known deferred work begins in Phase 6: database-side pgvector retrieval,
production voice provider hardening, structured complaint registry, transfer,
queue, dashboard mutation flows, and security hardening.

## Phase 6: Production Vector DB Retrieval

### Goal

Move Smart Similarity from pgvector-ready storage to true database-side vector
retrieval when Supabase is configured.

### Tasks

- [x] Add SQL RPC/function `match_resolved_cases` using pgvector cosine distance.
- [x] Add repository method for Supabase top-k vector search.
- [x] Query vector DB with:
  - [x] query embedding
  - [x] category filter
  - [x] language filter
  - [x] dialect filter when available
  - [x] urgency band filter
  - [x] similarity threshold
- [x] Backfill embeddings for existing resolved cases.
- [x] Add seed command for demo cases with embeddings.
- [x] Keep deterministic in-process fallback when Supabase/vector search is unavailable.
- [x] Add provider health output for vector DB readiness.

### Acceptance Criteria

- [x] Supabase pgvector returns top-k resolved cases without fetching all rows.
- [x] Mobile theft still matches the seeded mobile theft case through DB search.
- [x] Local fallback still works without Supabase.
- [x] Dashboard/API show whether the match came from `vector_db` or `local_fallback`.

### Phase 6 Verification

- [x] `.venv/bin/python -m compileall backend dashboard tests`
- [x] `.venv/bin/python -m pytest`
- [x] `.venv/bin/python -m ruff check backend dashboard tests`
- [x] `make PYTHON=.venv/bin/python smoke`
- [x] `.venv/bin/python -c "from backend.app import app; print(app.title)"`
- [x] `timeout 8s .venv/bin/python -m backend.main`

## Phase 7: Voice Pipeline Hardening

### Goal

Make the architecture image's phone-call path real, low-latency, and demo-safe:
Twilio/SIP audio in, streaming STT, analysis, Vachan, TTS audio back.

### Tasks

- [x] Move current STT functions into provider classes under `backend/voice/stt.py`.
- [x] Move current TTS functions into provider classes under `backend/voice/tts.py`.
- [x] Add provider order configuration for STT and TTS.
- [x] Add Bhashini STT/TTS primary provider support.
- [x] Add Deepgram STT fallback.
- [x] Add Google Cloud STT/TTS fallback where configured.
- [x] Add OpenAI Whisper/TTS fallback where configured.
- [x] Keep Edge TTS no-key fallback for local demos.
- [x] Add pre-generated phrase cache for common Vachan/routing phrases.
- [x] Add latency measurements:
  - [x] STT latency
  - [x] analysis latency
  - [x] vector search latency
  - [x] TTS latency
- [x] Add no-silence fallback when all TTS providers fail.
- [x] Add tests for provider fallback order.
- [x] Add one real phone-call smoke checklist using Twilio/ngrok.

### Acceptance Criteria

- [ ] One end-to-end call works through Twilio media stream.
      Manual verification is required after Twilio credentials and a public
      ngrok URL are configured.
- [x] Local text demo still works without voice provider keys.
- [x] Common phrases can be spoken from pre-generated cache.
- [x] STT/TTS latency is visible in audit events or metrics.
- [x] If a paid provider fails, Sahayak degrades gracefully instead of going silent.

### Phase 7 Twilio/ngrok Smoke Checklist

- [ ] Set real values in `.env`:
      `BASE_URL`, `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`,
      `TWILIO_PHONE_NUMBER`, and at least one useful STT/TTS provider key.
- [ ] Start backend locally:
      `.venv/bin/python -m backend.main`
- [ ] Expose backend:
      `ngrok http 8000`
- [ ] Update `.env` `BASE_URL` to the HTTPS ngrok URL and restart backend.
- [ ] Configure Twilio Voice webhook for the Sahayak number:
      `POST {BASE_URL}/twilio/incoming`
- [ ] Call the Twilio number or use `/api/call-me`.
- [ ] Confirm Twilio connects to:
      `wss://<ngrok-host>/twilio/media-stream`
- [ ] Speak one short English/Hindi/Kannada issue and confirm audit events:
      `stt_completed`, `analysis_completed`, `tts_completed`,
      `voice_turn_completed`.
- [ ] Trigger a fallback scenario by disabling one provider in
      `STT_PROVIDER_ORDER` or `TTS_PROVIDER_ORDER`, then confirm the cascade
      continues.
- [ ] Confirm no silence if all TTS providers fail: `tts_completed` should show
      `provider=fallback_tone`.

### Phase 7 Verification

- [x] `.venv/bin/python -m compileall backend dashboard tests`
- [x] `.venv/bin/python -m pytest tests/test_phase7_voice_pipeline.py`
- [x] `.venv/bin/python -m pytest`
- [x] `.venv/bin/python -m ruff check backend dashboard tests`
- [x] `make PYTHON=.venv/bin/python smoke`
- [x] `.venv/bin/python -c "from backend.app import app; print(app.title)"`
- [x] `timeout 8s .venv/bin/python -m backend.main`

## Phase 8: Complaint and Action Registry

### Goal

Make "AI resolved" mean a real structured action was created.

### Tasks

- [x] Add complaint service.
- [x] Generate readable complaint reference IDs.
- [x] Store structured complaint fields:
  - [x] category
  - [x] description
  - [x] location
  - [x] urgency
  - [x] language
  - [x] call SID
  - [x] transcript reference
  - [x] status
- [x] Add mock government registration payload for demo.
- [x] Add complaint timeline endpoint.

### Acceptance Criteria

- [x] AI-resolved call creates a complaint.
- [x] Complaint has a reference ID.
- [x] Dashboard shows complaint status and timeline.
- [x] API can list complaints without direct database access from dashboard.

### Phase 8 Verification

- [x] `.venv/bin/python -m compileall backend dashboard tests`
- [x] `.venv/bin/python -m pytest tests/test_phase8_complaints.py`
- [x] `.venv/bin/python -m pytest`
- [x] `.venv/bin/python -m ruff check backend dashboard tests`
- [x] `make PYTHON=.venv/bin/python smoke`
- [x] `.venv/bin/python -c "from backend.app import app; print(app.title)"`
- [x] `timeout 8s .venv/bin/python -m backend.main`

## Phase 9: Officer Routing and Warm Transfer

### Goal

Make human handover real and context-rich.

### Tasks

- [ ] Implement routing score:
  - [ ] 50 percent urgency/specialty fit
  - [ ] 40 percent language/dialect fit
  - [ ] 10 percent shortest wait time
  - [ ] load penalty
- [ ] Add handover context model.
- [ ] Add endpoint for officer accepting a handover.
- [ ] Add Twilio transfer/conference service abstraction.
- [ ] Keep mock transfer mode for local development.
- [ ] Add officer first-sentence suggestion.

### Acceptance Criteria

- [ ] Handover returns selected officer and score breakdown.
- [ ] Dashboard shows handover context.
- [ ] Local mock handover works without Twilio.
- [ ] Twilio mode can be enabled with credentials.

## Phase 10: Queue, Surge IVR, and High-Help Alert

### Goal

Handle high-volume surge cases safely.

### Tasks

- [x] Add priority queue manager.
- [x] Store queue entries durably.
- [x] Add queue position and wait timer.
- [x] Add DTMF actions:
  - [x] 1 for Police
  - [x] 2 for Ambulance
  - [x] 3 for Fire
- [x] Add configurable High-Help Alert timeout.
- [x] Make timeout shorter in demo mode.
- [x] Show queue state in dashboard.

### Acceptance Criteria

- [x] If no officer is available, caller enters queue.
- [x] DTMF redirect updates call outcome.
- [x] Queue timeout creates High-Help Alert.
- [x] Dashboard highlights High-Help Alert.

## Phase 11: Dashboard Upgrade

### Goal

Turn the dashboard into a convincing officer command center with a modern Next.js UI.

### Tasks

- [x] Replace UI-only correction buttons with real API calls.
- [x] Add live transcript endpoint usage.
- [x] Add AI reasoning panel.
- [x] Add Vachan status card.
- [x] Add similarity match card.
- [x] Add routing score breakdown.
- [x] Add queue and High-Help Alert panels.
- [x] Add knowledge-base learning event display.
- [x] Add backend health and provider health panel.

### Acceptance Criteria

- [x] Officer can correct category, urgency, summary, and resolution.
- [x] Corrections are stored as audit events.
- [x] Corrected human resolution can be added to knowledge base.
- [x] Dashboard supports all five competition demo scenarios.

## Phase 12: Security and Production Hardening

### Goal

Make the system credible for government/emergency deployment.

### Tasks

- [x] Validate Twilio webhook signatures.
- [x] Add dashboard authentication.
- [x] Add role-based authorization.
- [x] Add PII masking for phone numbers and sensitive text.
- [x] Add structured JSON logs.
- [x] Add rate limiting.
- [x] Add request IDs and call correlation IDs.
- [x] Add safe error responses.
- [x] Add data retention configuration.

### Acceptance Criteria

- [x] Public webhooks are validated.
- [x] Dashboard cannot mutate data without auth in production mode.
- [x] Logs avoid leaking full phone numbers by default.
- [x] All API errors return safe JSON.

## Phase 13: Bounded AI Agent Runtime

### Goal

Make Sahayak feel and operate like a real AI agent codebase while preserving the existing tested workflow.

### Tasks

- [x] Add `backend/agent/` package.
- [x] Add `SahayakAgent` runtime as the channel-facing entrypoint.
- [x] Add agent context, tool, result, and trace schemas.
- [x] Add explicit bounded tool registry.
- [x] Add policy explanation and safety notes.
- [x] Add memory/event persistence for agent turns.
- [x] Route text API pipeline through the agent.
- [x] Route Twilio voice turns through the agent.
- [x] Add agent tools and trace APIs.
- [x] Show agent traces in the dashboard.
- [x] Add agent runtime tests.

### Acceptance Criteria

- [x] Core decision workflow remains unchanged.
- [x] APIs and voice are channels into `SahayakAgent`.
- [x] Each turn can expose observe/tool/action/safety trace.
- [x] Existing tests continue to pass.

## Phase 14: End-to-End Demo Scripts

### Goal

Prepare a competition-safe demo with backup paths.

### Demo Scenarios

- [ ] AI resolves mobile theft automatically.
- [ ] Caller asks for human and is routed.
- [ ] Extreme urgency triggers immediate handover.
- [ ] No agents available triggers queue and IVR.
- [ ] Officer correction creates knowledge-base learning.

### Tasks

- [ ] Add seeded demo data for all scenarios.
- [ ] Add scripted test endpoint payloads.
- [ ] Add README demo instructions.
- [ ] Record fallback demo video.
- [ ] Add "demo mode" settings for shorter queue timeout and mock transfer.

### Acceptance Criteria

- [ ] Each demo scenario works from dashboard test pipeline.
- [ ] At least one scenario works through phone call if Twilio is configured.
- [ ] Demo can still run without paid providers using deterministic fallbacks.

## Phase 15: Evaluation and Polish

### Goal

Show measurable impact and polish the submission.

### Tasks

- [ ] Add metrics endpoint:
  - [ ] total calls
  - [ ] AI resolved count
  - [ ] handover count
  - [ ] queued count
  - [ ] average confidence
  - [ ] average urgency
  - [ ] average decision latency
- [ ] Add latency logging:
  - [ ] STT latency
  - [ ] NLU latency
  - [ ] similarity latency
  - [ ] TTS latency
- [ ] Update README architecture section.
- [ ] Add screenshots or architecture diagram reference.
- [ ] Add final competition pitch text.

### Acceptance Criteria

- [ ] Dashboard shows measurable impact.
- [ ] README explains local setup and production setup.
- [ ] Project can be evaluated by another developer from a fresh clone.

## Recommended Build Order

1. Phase 0: Project Stabilization
2. Phase 1: Modular Production Structure
3. Phase 2: Durable State and Audit Events
4. Phase 3: Structured Decision Engine
5. Phase 4: Smart Similarity Knowledge Base
6. Phase 5: Vachan Confirmation Loop
7. Phase 6: Production Vector DB Retrieval
8. Phase 7: Voice Pipeline Hardening
9. Phase 8: Complaint and Action Registry
10. Phase 9: Officer Routing and Warm Transfer
11. Phase 10: Queue, Surge IVR, and High-Help Alert
12. Phase 11: Dashboard Upgrade
13. Phase 12: Security and Production Hardening
14. Phase 13: Bounded AI Agent Runtime
15. Phase 14: End-to-End Demo Scripts
16. Phase 15: Evaluation and Polish

## Phase Completion Rule

Do not move to the next phase until:

- [ ] The app starts locally.
- [ ] Tests for the phase pass.
- [ ] Existing demo paths still work.
- [ ] New behavior is documented.
- [ ] Any fallback/mock behavior is clearly marked.

## Immediate Next Step

Start Phase 14: End-to-End Demo Scripts.

1. Add seeded demo scenarios.
2. Add demo reset/seed endpoint.
3. Add dashboard controls for scenario replay.
4. Validate one phone-call path if Twilio/provider keys are configured.
5. Keep deterministic fallback ready for competition demo safety.

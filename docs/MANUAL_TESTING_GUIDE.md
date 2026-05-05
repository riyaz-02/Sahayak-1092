# Sahayak 1092 Manual Testing Guide

This guide explains how to manually test Sahayak 1092 after Phase 12. It covers how the current project works, what to run, which APIs to use, and the safest order for checking every major feature.

## Current Project Shape

Sahayak 1092 currently has two main applications:

| App | Path | Purpose |
|---|---|---|
| FastAPI backend | `backend/` | AI pipeline, Twilio webhooks, voice stream, routing, queue, complaints, Supabase/vector DB, security |
| Next.js dashboard | `dashboard/app/` | Officer/admin command center for active calls, handovers, queue, complaints, and resolved-case learning |

The dashboard does not call the backend directly from browser code. It uses the Next.js server-side proxy:

```text
dashboard/app/api/sahayak/[...path]/route.ts
```

That proxy forwards dashboard requests to FastAPI and can safely attach the backend API key server-side.

## How the System Works

The current Sahayak flow is:

1. A citizen call or text test enters the backend.
2. The input enters `SahayakAgent`, the bounded emergency operations agent.
3. Agent loads call memory and records an agent turn start.
4. Analyzer detects language, sentiment, urgency, category, intent, and confidence.
5. Smart Similarity checks previously resolved cases using local fallback or Supabase pgvector.
6. Decision engine chooses one path:
   - High confidence: ask Vachan confirmation.
   - Confirmed: register complaint/action and close as AI-resolved.
   - Low confidence: ask clarification or route to human after configured attempts.
   - Caller asks for officer: route to human.
   - Extreme urgency/distress: immediate human handover path.
   - No officer available: priority queue with DTMF and High-Help Alert support.
7. Agent records approved tool calls, safety notes, memory writes, final action, and final phase.
8. Dashboard displays calls, summaries, agents, complaints, queue entries, agent traces, and knowledge-base actions.
9. Officers can toggle availability, accept handovers, correct AI output, and add resolved calls back to the knowledge base.

## Required Local Setup

### Backend Env

Your root `.env` should exist:

```bash
cp .env.example .env
```

For local manual testing, these values should be relaxed:

```env
SAHAYAK_ENV=development
DEBUG=true
DEMO_MODE=true
TRANSFER_MODE=mock
DASHBOARD_AUTH_REQUIRED=false
VALIDATE_TWILIO_SIGNATURES=false
ANALYSIS_PROVIDER=auto
EMBEDDING_PROVIDER=deterministic
```

For local text-only testing, provider keys may be blank. For realistic AI/voice behavior, configure provider keys.

If a live LLM key is configured but your network/provider is unavailable, set a short timeout so manual tests fall back quickly:

```env
LLM_PROVIDER_TIMEOUT_SEC=8
```

### Dashboard Env

Create `dashboard/.env.local`:

```env
SAHAYAK_API_URL=http://localhost:8000
NEXT_PUBLIC_SAHAYAK_API_URL=http://localhost:8000
SAHAYAK_DASHBOARD_API_KEY=
```

If you enable backend dashboard auth, set:

```env
SAHAYAK_DASHBOARD_API_KEY=same-value-as-backend-DASHBOARD_API_KEY
```

## Start the Project

Use two terminals.

### Terminal 1: Backend

```bash
source .venv/bin/activate
make PYTHON=.venv/bin/python dev-backend
```

Backend URLs:

```text
API:    http://localhost:8000
Health: http://localhost:8000/health
Docs:   http://localhost:8000/docs
```

### Terminal 2: Dashboard

```bash
make dev-dashboard
```

Dashboard URL:

```text
http://localhost:3000
```

## API Map

| Method | API | Purpose | When to test |
|---|---|---|---|
| `GET` | `/health` | Checks backend, Supabase/vector DB, Redis, voice, and security readiness | First |
| `GET` | `/` | Basic service metadata | First |
| `POST` | `/api/test-pipeline` | Main text-only pipeline test without real phone call | Core testing |
| `POST` | `/api/call-me` | Starts outbound Twilio call to a phone number | After Twilio setup |
| `POST` | `/twilio/incoming` | Twilio incoming voice webhook | Real phone testing |
| `POST` | `/twilio/status` | Twilio call status callback | Real phone testing |
| `WS` | `/twilio/media-stream` | Real-time Twilio voice stream | Real phone testing |
| `GET` | `/api/active-calls` | Active calls for dashboard | Dashboard testing |
| `GET` | `/api/call-logs` | Recent calls and summaries | After pipeline tests |
| `GET` | `/api/call-transcript/{call_sid}` | Transcript for one call | After a test call |
| `GET` | `/api/call-events?call_sid=...` | Audit trail for one call | Debugging and demo |
| `GET` | `/api/agent/tools` | Shows the bounded tools Sahayak is allowed to use | Agent validation |
| `GET` | `/api/agent/traces?call_sid=...` | Shows observe/tool/action/safety trace for agent turns | Agent validation |
| `GET` | `/api/agents` | Officer list and availability | Handover testing |
| `POST` | `/api/agent/toggle` | Toggle officer availability | Queue/handover testing |
| `POST` | `/api/handover/{call_sid}/accept` | Officer accepts warm handover | Handover testing |
| `GET` | `/api/complaints` | Registered complaints/actions | Vachan confirmation testing |
| `GET` | `/api/complaints/{reference_id}/timeline` | Timeline for one complaint | Complaint audit testing |
| `GET` | `/api/resolved-cases` | Knowledge base of resolved cases | Similarity testing |
| `POST` | `/api/resolved-cases/from-call` | Add corrected call resolution into knowledge base | Learning-loop testing |
| `POST` | `/api/calls/{call_sid}/corrections` | Store officer correction for a call | Officer feedback testing |
| `GET` | `/api/queue` | Priority queue entries | Surge testing |
| `GET` | `/api/queue/{call_sid}` | Queue state for one call | Surge testing |

## Manual Testing Order

Follow this order. It catches problems early and avoids debugging everything at once.

### 1. Health Check

```bash
curl http://localhost:8000/health
```

Expected:

- Backend returns JSON.
- `status` should be present.
- Supabase/vector DB may show unavailable if not configured, but app should still run in local fallback mode.
- Security settings should reflect local demo mode.

### 2. Root Metadata

```bash
curl http://localhost:8000/
```

Expected:

- Basic service metadata.
- No server error.

### 3. Dashboard Loads

Open:

```text
http://localhost:3000
```

Expected:

- Dashboard opens.
- No blank page.
- It should show current system state, calls, agents, complaints, queue, or empty states gracefully.

### 4. Normal AI-Resolved Complaint Flow

Send a normal issue:

```bash
curl -X POST http://localhost:8000/api/test-pipeline \
  -H "Content-Type: application/json" \
  -d '{"call_sid":"manual-theft-1","text":"My mobile phone was stolen at Majestic bus stand","language":"english"}'
```

Expected:

- Response includes analysis fields.
- Sahayak should ask for Vachan confirmation or produce a next-step response.
- Dashboard should show/update the call.

Confirm:

```bash
curl -X POST http://localhost:8000/api/test-pipeline \
  -H "Content-Type: application/json" \
  -d '{"call_sid":"manual-theft-1","text":"yes","language":"english"}'
```

Expected:

- Complaint/action gets registered.
- Outcome should move toward AI-resolved.

Check complaints:

```bash
curl http://localhost:8000/api/complaints
```

Check audit trail:

```bash
curl "http://localhost:8000/api/call-events?call_sid=manual-theft-1&limit=50"
```

Check agent trace:

```bash
curl "http://localhost:8000/api/agent/traces?call_sid=manual-theft-1&limit=10"
```

Expected:

- Trace includes `sahayak_1092`.
- Tool calls include `load_call_memory`, `understand_caller`, `evaluate_safety_policy`, and `request_vachan_confirmation`.
- Safety notes explain why the agent continued, confirmed, handed over, or queued.

Check bounded tools:

```bash
curl http://localhost:8000/api/agent/tools
```

Expected:

- Tool list is explicit and bounded.
- There is no unrestricted arbitrary action tool.

### 5. Vachan Rejection Flow

Start a new call:

```bash
curl -X POST http://localhost:8000/api/test-pipeline \
  -H "Content-Type: application/json" \
  -d '{"call_sid":"manual-vachan-no-1","text":"There is loud music near my house at midnight","language":"english"}'
```

Reject:

```bash
curl -X POST http://localhost:8000/api/test-pipeline \
  -H "Content-Type: application/json" \
  -d '{"call_sid":"manual-vachan-no-1","text":"no, that is wrong","language":"english"}'
```

Expected:

- Sahayak should not register final action blindly.
- It should ask for correction or clarification.
- Audit events should include rejected/clarification behavior.

### 6. Partial Correction Flow

```bash
curl -X POST http://localhost:8000/api/test-pipeline \
  -H "Content-Type: application/json" \
  -d '{"call_sid":"manual-partial-1","text":"Someone is following me near Indiranagar metro","language":"english"}'
```

Then:

```bash
curl -X POST http://localhost:8000/api/test-pipeline \
  -H "Content-Type: application/json" \
  -d '{"call_sid":"manual-partial-1","text":"partly correct, the location is MG Road metro","language":"english"}'
```

Expected:

- Sahayak applies correction.
- It should reconfirm before final registration.

### 7. Human Request Flow

```bash
curl -X POST http://localhost:8000/api/test-pipeline \
  -H "Content-Type: application/json" \
  -d '{"call_sid":"manual-human-1","text":"I want to speak to a police officer immediately","language":"english"}'
```

Expected:

- Decision should enter handover path.
- If an officer is available, warm handover context should be created.
- If no officer is available, queue entry should be created.

Check:

```bash
curl http://localhost:8000/api/active-calls
curl "http://localhost:8000/api/call-events?call_sid=manual-human-1&limit=50"
```

### 8. Extreme Urgency Flow

```bash
curl -X POST http://localhost:8000/api/test-pipeline \
  -H "Content-Type: application/json" \
  -d '{"call_sid":"manual-urgent-1","text":"Help me, I am in danger and someone is attacking me","language":"english"}'
```

Expected:

- Sahayak should prioritize human handover or urgent queue.
- It should not treat this as a routine autonomous complaint.

### 9. Agent Availability Flow

List agents:

```bash
curl http://localhost:8000/api/agents
```

Toggle an agent:

```bash
curl -X POST http://localhost:8000/api/agent/toggle \
  -H "Content-Type: application/json" \
  -d '{"agent_id":"AGENT_ID_FROM_RESPONSE","available":false}'
```

Expected:

- Agent availability changes.
- Dashboard reflects the change.

### 10. Queue Flow

Make all agents unavailable from dashboard or API, then trigger human-request or urgent call.

Check queue:

```bash
curl http://localhost:8000/api/queue
```

Check one entry:

```bash
curl http://localhost:8000/api/queue/manual-human-1
```

Expected:

- Queue entry exists.
- It has priority score, status, position, estimated wait, and service target.

### 11. Handover Acceptance Flow

If a call is waiting for handover:

```bash
curl -X POST http://localhost:8000/api/handover/manual-human-1/accept \
  -H "Content-Type: application/json" \
  -d '{"agent_id":"AGENT_ID_FROM_RESPONSE"}'
```

Expected:

- Handover is accepted.
- Call state and logs update.
- Audit event is created.

### 12. Resolved-Case Learning Flow

After a call has enough context, store an officer correction:

```bash
curl -X POST http://localhost:8000/api/calls/manual-theft-1/corrections \
  -H "Content-Type: application/json" \
  -d '{"corrected_summary":"Mobile theft reported at Majestic bus stand","corrected_resolution":"Register theft complaint and advise caller to block SIM and preserve IMEI details","agent_id":"demo-agent"}'
```

Add the corrected call to knowledge base:

```bash
curl -X POST http://localhost:8000/api/resolved-cases/from-call \
  -H "Content-Type: application/json" \
  -d '{"call_sid":"manual-theft-1","resolution":"Register theft complaint and advise caller to block SIM and preserve IMEI details","agent_id":"demo-agent"}'
```

Check:

```bash
curl http://localhost:8000/api/resolved-cases
```

Expected:

- New or updated resolved case appears.
- Future similar calls can match against it.

## Supabase and Vector DB Manual Checks

If Supabase is configured:

1. Run schema:

```text
backend/persistence/models.sql
```

2. Seed demo cases:

```bash
make PYTHON=.venv/bin/python seed-vector-cases
```

3. Backfill embeddings:

```bash
make PYTHON=.venv/bin/python backfill-vector-embeddings
```

4. Check health:

```bash
curl http://localhost:8000/health
```

5. Check knowledge base:

```bash
curl http://localhost:8000/api/resolved-cases
```

Expected:

- `resolved_cases` should contain demo cases.
- Vector DB health should not be broken.
- Similarity calls should mention matched/adapted resolved cases when appropriate.

## Twilio Live Call Manual Test

Only do this after text-only pipeline and dashboard are working.

### 1. Start backend

```bash
make PYTHON=.venv/bin/python dev-backend
```

### 2. Start ngrok

```bash
ngrok http 8000
```

### 3. Update `.env`

```env
BASE_URL=https://your-ngrok-domain.ngrok-free.app
TWILIO_ACCOUNT_SID=your_twilio_sid
TWILIO_AUTH_TOKEN=your_twilio_auth_token
TWILIO_PHONE_NUMBER=your_twilio_number
TRANSFER_MODE=twilio
```

For public webhook safety:

```env
VALIDATE_TWILIO_SIGNATURES=true
```

Restart backend after changing `.env`.

### 4. Configure Twilio

Set Twilio phone number voice webhook:

```text
POST https://your-ngrok-domain.ngrok-free.app/twilio/incoming
```

Expected Twilio media stream:

```text
wss://your-ngrok-domain.ngrok-free.app/twilio/media-stream
```

### 5. Test Call

Call the Twilio number and speak a simple issue first:

```text
My phone was stolen near Majestic bus stand.
```

Expected:

- Backend receives incoming call.
- Media stream connects.
- Transcript/analysis events are created.
- Dashboard updates.

## Production-Like Local Security Test

Set backend:

```env
DEMO_MODE=false
DASHBOARD_AUTH_REQUIRED=true
DASHBOARD_API_KEY=test-secret-key
VALIDATE_TWILIO_SIGNATURES=false
```

Set dashboard:

```env
SAHAYAK_DASHBOARD_API_KEY=test-secret-key
```

Restart backend and dashboard.

Manual API without key should fail:

```bash
curl http://localhost:8000/api/agents
```

Manual API with key should work:

```bash
curl http://localhost:8000/api/agents \
  -H "X-Sahayak-API-Key: test-secret-key"
```

Dashboard should continue working because the Next.js proxy sends the key.

## Common Failure Points

| Symptom | Likely cause | Fix |
|---|---|---|
| Dashboard blank or fetch errors | Backend not running or wrong `SAHAYAK_API_URL` | Start backend and check `dashboard/.env.local` |
| `/api/*` returns 401 | `DASHBOARD_AUTH_REQUIRED=true` but key missing | Set `SAHAYAK_DASHBOARD_API_KEY` |
| Twilio call does not connect | `BASE_URL` not public or webhook wrong | Use ngrok HTTPS URL and update Twilio webhook |
| Twilio signature fails | `BASE_URL` mismatch or ngrok changed | Update `.env`, restart backend, update Twilio |
| No Supabase records | Supabase env missing or schema not applied | Run `models.sql`, check `SUPABASE_URL` and `SUPABASE_KEY` |
| Vector search weak | Deterministic embeddings or no seeded cases | Seed cases and use provider embeddings for production |
| Voice response slow | Provider key missing or timeout fallback | Configure Bhashini/Deepgram/TTS providers |
| Queue not showing | Agents still available or call did not trigger handover | Toggle agents unavailable and trigger human/urgent call |

## Final Manual Testing Checklist

- [ ] Backend starts.
- [ ] Dashboard starts.
- [ ] `/health` works.
- [ ] Dashboard loads without blank/error state.
- [ ] Text-only normal complaint creates Vachan prompt.
- [ ] `/api/agent/tools` returns bounded tool registry.
- [ ] `/api/agent/traces` shows observe/tool/action/safety trace.
- [ ] Vachan `yes` creates complaint.
- [ ] Vachan `no` asks for correction.
- [ ] Partial confirmation updates and reconfirms.
- [ ] Human request triggers handover path.
- [ ] Extreme urgency avoids autonomous routine resolution.
- [ ] Agent toggle works.
- [ ] Queue works when no agent is available.
- [ ] Handover accept works.
- [ ] Correction endpoint records officer feedback.
- [ ] Resolved-case learning endpoint adds knowledge.
- [ ] Supabase stores records when configured.
- [ ] Vector cases seed/backfill works.
- [ ] Dashboard reflects active calls, queue, complaints, and knowledge base.
- [ ] Production-like dashboard auth works.
- [ ] Twilio live call works, if configured.

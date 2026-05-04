<p align="center">
  <h1 align="center">🚨 Sahayak 1092</h1>
  <p align="center"><strong>Every Voice Heard. Every Call Resolved. Every Second Counts.</strong></p>
  <p align="center">AI-first voice-to-voice system for India's 1092 Emergency Helpline</p>
  <p align="center">
    <em>AI for Bharat 2026 · Theme 12: AI for 1092 Helpline</em>
  </p>
</p>

---

## 🎯 What is Sahayak 1092?

When someone dials **1092**, they want fast, accurate help — not long waits or repeated explanations to an officer who may not fully understand their dialect or emotion.

**Sahayak 1092** is an AI-first voice-to-voice system that takes full control from the first ring and resolves most calls end-to-end automatically. Only in genuine exception cases does it hand over seamlessly to the nearest available officer.

### Key Innovations

| Feature | Description |
|---------|-------------|
| 🗣️ **Multilingual Voice AI** | Answers instantly in Kannada, Hindi, or English — detects language and dialect automatically |
| 🧠 **Smart Similarity Detection** | Matches against previous human-resolved cases. If similar, resolves automatically without handover |
| ✅ **Vachan (Confirmation Loop)** | Always restates understanding and asks for yes/no confirmation before final action |
| 📊 **Urgency-First Routing** | 50% urgency + 40% language/dialect fit + 10% shortest wait — when handover is needed |
| 🚨 **High-Help Alert** | 2-minute queue timeout auto-transfers to police as critical alert |
| 📱 **Surge IVR** | Press 1 for Police, 2 for Ambulance, 3 for Fire — instant redirect while in queue |

---

## 📞 Complete Call Flow

```
Caller dials 1092 (Twilio)
        │
        ▼
┌───────────────────────────────────┐
│  Sahayak answers instantly        │
│  Greets in Kannada/Hindi/English  │
└──────────────┬────────────────────┘
               │
               ▼
┌───────────────────────────────────┐
│  Citizen speaks freely            │
│  Real-time STT via Bhashini/      │
│  Deepgram/Whisper                 │
└──────────────┬────────────────────┘
               │
               ▼
┌───────────────────────────────────┐
│  AI Decision Engine analyses:     │
│  • Language & dialect             │
│  • Sentiment & urgency            │
│  • Confidence score               │
│  • Category classification        │
└──────────────┬────────────────────┘
               │
        ┌──────┴──────┐
        ▼             ▼
   HIGH CONF.     HANDOVER NEEDED
   (≥ 0.7)       (3 conditions)
        │             │
        ▼             ▼
┌──────────────┐ ┌──────────────────┐
│ Similarity   │ │ Conditions:      │
│ Detection    │ │ • Low conf (×2)  │
│ against KB   │ │ • Caller asks    │
│              │ │ • Extreme urgency│
│ If match ≥70%│ └────────┬─────────┘
│ → Auto-solve │          │
└──────┬───────┘    ┌─────┴─────┐
       │            ▼           ▼
       ▼       AGENT FOUND   NO AGENT
┌──────────────┐    │           │
│ VACHAN LOOP  │    ▼           ▼
│ "Is this     │  Warm       Queue +
│  correct?    │  Transfer   IVR Surge
│  Yes / No"   │  + Summary  Handling
└──────┬───────┘  + Transcript
       │
  YES  │  NO
   │   │   │
   ▼   │   ▼
RESOLVE│  RE-LISTEN
+ FIR  │
+ KB   │
```

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        TWILIO CLOUD                              │
│   Caller ──► Toll-Free Number ──► Webhook ──► Media Stream WS   │
└─────────────────────────────────┬───────────────────────────────┘
                                  │
                    ┌─────────────▼─────────────┐
                    │    FastAPI Backend         │
                    │                            │
                    │  ┌──────────────────────┐  │
                    │  │  Media Stream Handler │  │  Twilio mulaw ↔ PCM
                    │  │  (WebSocket)          │  │
                    │  └──────────┬───────────┘  │
                    │             │               │
                    │  ┌──────────▼───────────┐  │
                    │  │  STT Pipeline         │  │  Bhashini → Deepgram → Whisper
                    │  └──────────┬───────────┘  │
                    │             │               │
                    │  ┌──────────▼───────────┐  │
                    │  │  Decision Engine      │  │  GPT-4o / Grok
                    │  │  • Analyse            │  │  Language, Sentiment, Urgency
                    │  │  • Similarity Match   │  │  KB Matching
                    │  │  • Route / Resolve    │  │  Agent Scoring
                    │  │  • Vachan Loop        │  │  Confirmation
                    │  └──────────┬───────────┘  │
                    │             │               │
                    │  ┌──────────▼───────────┐  │
                    │  │  TTS Pipeline         │  │  Bhashini → OpenAI TTS
                    │  └──────────┬───────────┘  │
                    │             │               │
                    │  ┌──────────▼───────────┐  │
                    │  │  Supabase Client      │  │  Cases, Agents, Logs, Complaints
                    │  └──────────────────────┘  │
                    └────────────────────────────┘
                                  │
                    ┌─────────────▼─────────────┐
                    │  Streamlit Dashboard       │
                    │  Live Calls · Agents ·     │
                    │  History · KB · Complaints  │
                    └────────────────────────────┘
```

---

## 🛠️ Tech Stack

| Component | Technology |
|-----------|-----------|
| **Backend** | FastAPI + Python 3.11+ |
| **Telephony** | Twilio Voice + Media Streams WebSocket |
| **STT (Primary)** | Bhashini / VoicERA (Indian languages) |
| **STT (Fallback)** | Deepgram Nova-2, OpenAI Whisper |
| **TTS (Primary)** | Bhashini (natural Indian voice) |
| **TTS (Fallback)** | OpenAI TTS (nova voice) |
| **NLU / LLM** | OpenAI GPT-4o or Grok (via compatible API) |
| **Database** | Supabase (PostgreSQL) |
| **Dashboard** | Streamlit |
| **Tunnel** | ngrok (for local development) |

---

## 📁 Project Structure

```
sahayak-1092/
├── backend/
│   ├── __init__.py
│   ├── main.py                 # FastAPI app — Twilio webhooks, REST APIs, WebSocket
│   ├── media_stream.py         # Real-time audio: Twilio ↔ STT ↔ LLM ↔ TTS
│   ├── decision_engine.py      # Language/sentiment/urgency + Vachan + Similarity + Routing
│   └── supabase_client.py      # DB schema, CRUD, seed data
├── dashboard/
│   ├── __init__.py
│   └── app.py                  # Streamlit command center dashboard
├── .env.example                # Environment variable template
├── requirements.txt            # Python dependencies
└── README.md                   # This file
```

---

## 🚀 Quick Start

### Prerequisites

- **Python 3.11+**
- **ngrok** account (free) — [ngrok.com](https://ngrok.com)
- **Twilio** account with toll-free number
- **Supabase** project (free tier works)
- **OpenAI** API key (or Grok-compatible key)
- Optionally: **Bhashini** API key, **Deepgram** API key

### Step 1: Clone & Install

```bash
git clone https://github.com/your-repo/sahayak-1092.git
cd sahayak-1092

# Create virtual environment
python -m venv venv

# Activate (Windows)
venv\Scripts\activate

# Activate (Mac/Linux)
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Step 2: Configure Environment

```bash
# Copy the template
cp .env.example .env

# Edit .env with your actual keys
notepad .env   # Windows
# nano .env    # Linux/Mac
```

**Required keys:**
| Key | Where to get it |
|-----|----------------|
| `TWILIO_ACCOUNT_SID` | [Twilio Console](https://console.twilio.com/) |
| `TWILIO_AUTH_TOKEN` | Twilio Console |
| `TWILIO_PHONE_NUMBER` | Your Twilio toll-free number |
| `OPENAI_API_KEY` | [OpenAI Platform](https://platform.openai.com/) |
| `SUPABASE_URL` | [Supabase Dashboard](https://supabase.com/dashboard) → Settings → API |
| `SUPABASE_KEY` | Supabase Dashboard → Settings → API (anon public key) |
| `BASE_URL` | Your ngrok HTTPS URL (set after Step 4) |

**Optional keys (for enhanced Indian language support):**
| Key | Where to get it |
|-----|----------------|
| `BHASHINI_API_KEY` | [Bhashini Platform](https://bhashini.gov.in/) |
| `DEEPGRAM_API_KEY` | [Deepgram Console](https://console.deepgram.com/) |

### Step 3: Setup Supabase Database

1. Go to your Supabase project → **SQL Editor**
2. Copy the SQL from `backend/supabase_client.py` (the `BOOTSTRAP_SQL` constant)
3. Run it in the SQL editor to create all tables
4. The app will auto-seed demo agents and resolved cases on first start

**Tables created:**
- `resolved_cases` — Knowledge base for similarity matching
- `agents` — Human officers with language skills
- `call_logs` — Per-call transcript, analysis, outcome
- `complaints` — Registered complaints linked to calls

### Step 4: Start ngrok Tunnel

```bash
# In a separate terminal
ngrok http 8000
```

Copy the **HTTPS** forwarding URL (e.g., `https://abc123.ngrok-free.app`) and:
1. Set `BASE_URL` in your `.env` file
2. Configure it as the Twilio webhook (Step 5)

### Step 5: Configure Twilio Webhook

1. Go to [Twilio Console](https://console.twilio.com/) → Phone Numbers → Your number
2. Under **Voice & Fax → A CALL COMES IN**:
   - Set to **Webhook**
   - URL: `https://your-ngrok-url.ngrok-free.app/twilio/incoming`
   - Method: **POST**
3. Under **Status Callback URL** (optional):
   - URL: `https://your-ngrok-url.ngrok-free.app/twilio/status`
   - Method: **POST**
4. Save

### Step 6: Start the Backend

```bash
# From project root
python -m backend.main
```

Or:

```bash
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

You should see:
```
============================================================
🚀 Sahayak 1092 – Starting up...
   Base URL : https://your-ngrok-url.ngrok-free.app
   Twilio # : +18666212451
============================================================
✅ Seeded demo agents
✅ Seeded demo resolved cases
```

### Step 7: Start the Dashboard

```bash
# In a separate terminal
streamlit run dashboard/app.py
```

Dashboard opens at `http://localhost:8501`

---

## 🧪 Testing Guide

### Test 1: Health Check

```bash
curl http://localhost:8000/health
```

Expected:
```json
{"status": "healthy", "service": "Sahayak 1092", "version": "1.0.0", "active_calls": 0}
```

### Test 2: AI Pipeline (No Phone Needed)

Use the `/api/test-pipeline` endpoint to test the full AI decision pipeline:

```bash
# English - Theft report
curl -X POST http://localhost:8000/api/test-pipeline \
  -H "Content-Type: application/json" \
  -d '{"text": "My phone was stolen at the bus stand", "language": "english"}'

# Kannada - Domestic violence (high urgency)
curl -X POST http://localhost:8000/api/test-pipeline \
  -H "Content-Type: application/json" \
  -d '{"text": "ನನ್ನ ಗಂಡ ನನ್ನನ್ನು ಹೊಡೆಯುತ್ತಿದ್ದಾನೆ, ದಯವಿಟ್ಟು ಸಹಾಯ ಮಾಡಿ", "language": "kannada"}'

# Hindi - Request for human
curl -X POST http://localhost:8000/api/test-pipeline \
  -H "Content-Type: application/json" \
  -d '{"text": "मुझे इंसान से बात करनी है, AI से नहीं", "language": "hindi"}'

# Confirmation test (use same call_sid)
curl -X POST http://localhost:8000/api/test-pipeline \
  -H "Content-Type: application/json" \
  -d '{"text": "yes that is correct", "call_sid": "test-confirm-1", "language": "english"}'
```

### Test 3: Dashboard Test Pipeline

1. Open `http://localhost:8501`
2. Navigate to **🧪 Test Pipeline** in the sidebar
3. Type a message in any language
4. Click **Send to Sahayak**
5. See real-time AI analysis: response, action, urgency, confidence, sentiment

### Test 4: Live Phone Call

1. Ensure ngrok is running and Twilio webhook is configured
2. Dial your Twilio toll-free number: **(866) 621-2451**
3. Wait for Sahayak's greeting
4. Speak your issue in Kannada, Hindi, or English
5. Watch the dashboard for live updates

---

## 🎬 Demo Scenarios

### Scenario 1: AI Resolves Automatically (Happy Path)

1. **Call in** and say: _"My mobile phone was stolen at Majestic bus stand"_
2. **Sahayak** detects: English, theft category, moderate urgency
3. **Similarity Match** finds a matching resolved case (mobile theft at bus stand)
4. **Sahayak** proposes resolution: _"I understand your phone was stolen. I'm registering an FIR. Please block your SIM. Your nearest station is..."_
5. **Vachan Loop**: _"Is this correct? Please say yes or no."_
6. **Caller says**: _"Yes"_
7. **Sahayak** confirms: _"Complaint registered. Reference: SAH-ABC123. An officer will follow up within 30 minutes."_
8. **Result**: Call resolved entirely by AI. Added to knowledge base. ✅

### Scenario 2: Handover — Caller Requests Human

1. **Call in** and say: _"मुझे इंसान से बात करनी है"_ (I want to talk to a human)
2. **Sahayak** detects: Hindi, caller wants human
3. **Agent Routing**: Finds best match (Hindi-speaking, lowest wait)
4. **Warm Transfer**: _"I'm connecting you to Inspector Pradeep Singh now. I've shared your details with them."_
5. **Agent Dashboard** shows: transcript, summary, sentiment, one-click correction buttons

### Scenario 3: Handover — Extreme Urgency

1. **Call in** with distressed voice: _"ನನ್ನ ಗಂಡ ನನ್ನನ್ನು ಹೊಡೆಯುತ್ತಿದ್ದಾನೆ!"_ (My husband is hitting me!)
2. **Sahayak** detects: Kannada, domestic, urgency 0.95, distressed
3. **Immediate handover** triggered (extreme urgency + distress)
4. **Routes to**: Language-matched + domestic violence specialist
5. **Dashboard**: Red urgency bar, distressed badge, full context for officer

### Scenario 4: Queue + IVR Surge

1. All agents are busy (set all agents to "Busy" in dashboard)
2. **Call in** with an issue
3. **Handover triggered** but no agents available
4. **Sahayak**: _"All officers are currently busy. You are in priority queue. Press 1 for Police, 2 for Ambulance, 3 for Fire."_
5. **Press 1** → Immediate redirect to Police
6. **No response for 2 min** → Auto-transfer as "High-Help Alert"

### Scenario 5: Low Confidence (Retry + Handover)

1. **Call in** with unclear/mixed language speech
2. **Sahayak** detects: Low confidence (< 0.5), attempt 1
3. **Sahayak**: _"I didn't quite understand. Could you please repeat your concern?"_
4. **Speak again** (still unclear)
5. **Sahayak**: Attempt 2, still low confidence → triggers handover
6. **Routes to agent** with full transcript of both attempts

---

## 📡 API Reference

### Twilio Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/twilio/incoming` | Webhook for incoming calls (returns TwiML) |
| `POST` | `/twilio/status` | Status callback (ringing, completed, etc.) |
| `WS` | `/twilio/media-stream` | Bidirectional WebSocket for audio |

### Dashboard / REST API

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/test-pipeline` | Test AI pipeline with text (no phone) |
| `GET` | `/api/active-calls` | Currently active calls (in-memory) |
| `GET` | `/api/call-logs` | Recent call logs from database |
| `GET` | `/api/agents` | All registered agents |
| `POST` | `/api/agent/toggle` | Toggle agent availability |
| `GET` | `/api/complaints` | Registered complaints |
| `GET` | `/api/resolved-cases` | Knowledge base of resolved cases |
| `GET` | `/health` | Health check |

---

## 🔧 Configuration Options

### Switching to Grok (instead of OpenAI)

```env
OPENAI_API_KEY=your_grok_api_key
OPENAI_BASE_URL=https://api.x.ai/v1
LLM_MODEL=grok-2
```

### STT/TTS Priority

The system automatically cascades through providers:

**STT**: Bhashini → Deepgram → OpenAI Whisper
**TTS**: Bhashini → OpenAI TTS

If a provider's API key is not set, it's skipped automatically.

---

## 🤝 Handover Logic (Detailed)

### Three handover conditions (and ONLY these):

1. **Low Confidence** — AI can't understand the caller after 2 attempts
2. **Caller Requests Human** — Explicit request ("I want to speak to an officer")
3. **Extreme Urgency + Distress** — Urgency ≥ 0.9 AND sentiment is distressed/angry

### Agent Scoring Formula

```
Score = (0.50 × Specialty Match) + (0.40 × Language Match) + (0.10 × Wait Time Score)
```

- **Specialty Match (50%)**: Agent's specialties include the call's category
- **Language Match (40%)**: Agent speaks the caller's language
- **Wait Time (10%)**: Lower average wait time → higher score
- **Load Penalty**: -15% if agent has > 2 active calls

### Warm Transfer Includes

- ✅ Full live transcript
- ✅ AI-generated summary
- ✅ Sentiment flag
- ✅ Urgency score
- ✅ One-click correction buttons (on dashboard)

---

## 🗄️ Database Schema

### `resolved_cases`
| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| summary | TEXT | Issue description |
| category | TEXT | theft, domestic, accident, etc. |
| language | TEXT | kannada, hindi, english |
| resolution | TEXT | How it was resolved |
| tags | TEXT[] | Searchable tags |
| created_at | TIMESTAMPTZ | Auto-set |

### `agents`
| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| name | TEXT | Officer name |
| badge_id | TEXT | Unique badge number |
| phone | TEXT | Contact number |
| languages | TEXT[] | Spoken languages |
| specialties | TEXT[] | domestic, cyber, traffic, etc. |
| is_available | BOOLEAN | Currently online |
| current_load | INT | Active call count |
| avg_wait_sec | INT | Average wait time |

### `call_logs`
| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| call_sid | TEXT | Twilio Call SID |
| caller_number | TEXT | Caller's phone |
| language | TEXT | Detected language |
| sentiment | TEXT | calm, anxious, distressed, angry |
| urgency | FLOAT | 0.0 – 1.0 |
| confidence | FLOAT | 0.0 – 1.0 |
| transcript | JSONB | Full conversation log |
| ai_summary | TEXT | AI-generated summary |
| outcome | TEXT | ai_resolved, handed_over, queued |

### `complaints`
| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| call_log_id | UUID | Links to call_logs |
| category | TEXT | Issue category |
| description | TEXT | Full description |
| status | TEXT | registered, in_progress, resolved |

---

## 🛡️ Production Considerations

For a production deployment, add:

- [ ] **Authentication** on dashboard and APIs
- [ ] **pgvector** embeddings for true semantic similarity search
- [ ] **Redis** for call state (instead of in-memory dict)
- [ ] **Twilio Conference** for actual warm transfers
- [ ] **Rate limiting** on all endpoints
- [ ] **SSL/TLS** in production (not just ngrok)
- [ ] **Logging** with structured JSON logs (ELK/Datadog)
- [ ] **Monitoring** with Prometheus/Grafana
- [ ] **Load testing** with Locust
- [ ] **Multi-region** deployment for low latency

---

## 📄 License

Built for **AI for Bharat 2026** Hackathon — Theme 12: AI for 1092 Helpline.

---

<p align="center">
  <strong>Sahayak 1092</strong> · Built with ❤️ for Bharat
</p>
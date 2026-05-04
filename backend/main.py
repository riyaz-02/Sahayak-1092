"""
Sahayak 1092 – Main FastAPI Application
=========================================
Entry point for the AI-first 1092 helpline system.

Endpoints:
  POST /twilio/incoming     – Twilio webhook for incoming calls
  POST /twilio/status       – Twilio status callbacks
  WS   /twilio/media-stream – Real-time audio WebSocket
  POST /api/test-pipeline   – Test the AI pipeline without a phone call
  GET  /api/active-calls    – Active calls for dashboard
  GET  /api/call-logs       – Recent call logs
  GET  /api/agents          – Agent list
  POST /api/agent/toggle    – Toggle agent availability
  GET  /api/complaints      – Complaints list
  GET  /api/resolved-cases  – Knowledge base
  GET  /health              – Health check
"""

import os
import sys
import json
import asyncio
from contextlib import asynccontextmanager

# Fix Windows console encoding for Unicode
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from fastapi import FastAPI, Request, WebSocket, HTTPException
from fastapi.responses import JSONResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from twilio.twiml.voice_response import VoiceResponse, Connect, Stream
from twilio.rest import Client as TwilioClient

from backend.media_stream import handle_media_stream
from backend.decision_engine import (
    process_caller_input,
    get_or_create_call,
    get_greeting,
    active_calls,
)
from backend import supabase_client as db

load_dotenv()

BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER", "+18666212451")
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")

# Twilio REST client for outbound calls
twilio_client = None
if TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN:
    twilio_client = TwilioClient(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)


# ── Lifespan ─────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown tasks."""
    print("=" * 60)
    print("[START] Sahayak 1092 - Starting up...")
    print(f"   Base URL : {BASE_URL}")
    print(f"   Twilio # : {TWILIO_PHONE_NUMBER}")
    print("=" * 60)

    # Seed demo data
    try:
        await db.seed_demo_data()
    except Exception as e:
        print(f"[WARN] Seed error (non-fatal): {e}")

    yield  # app running

    print("[STOP] Sahayak 1092 - Shutting down...")


# ── App ──────────────────────────────────────
app = FastAPI(
    title="Sahayak 1092",
    description="AI-first voice-to-voice system for India's 1092 emergency helpline",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ──────────────────────────────────────────────
# TWILIO WEBHOOK: INCOMING CALL
# ──────────────────────────────────────────────

@app.post("/twilio/incoming")
async def twilio_incoming(request: Request):
    """
    Twilio calls this when someone dials the 1092 number.
    We answer instantly and start a bidirectional Media Stream.
    """
    try:
        form = await request.form()
        call_sid = form.get("CallSid", "unknown")
        caller = form.get("From", "unknown")
        called = form.get("To", TWILIO_PHONE_NUMBER)

        print(f"\n{'='*60}")
        print(f"[CALL] INCOMING CALL")
        print(f"   From     : {caller}")
        print(f"   To       : {called}")
        print(f"   CallSid  : {call_sid}")
        print(f"{'='*60}\n")

        # Build TwiML — Connect to bidirectional Media Stream
        response = VoiceResponse()
        response.pause(length=1)

        ws_url = BASE_URL.replace("https://", "wss://").replace("http://", "ws://")
        connect = Connect()
        stream = Stream(url=f"{ws_url}/twilio/media-stream")
        stream.parameter(name="callerNumber", value=caller)
        connect.append(stream)
        response.append(connect)

        # After stream ends naturally, hang up cleanly (no error message)
        response.hangup()

        twiml = str(response)
        print(f"[TWIML] {twiml[:200]}")
        return Response(content=twiml, media_type="application/xml")

    except Exception as e:
        print(f"[ERROR] twilio_incoming failed: {e}")
        # Return minimal valid TwiML so Twilio doesn't play its own error
        fallback = VoiceResponse()
        fallback.say("Sahayak 1092. Please hold.", voice="Polly.Aditi", language="en-IN")
        fallback.hangup()
        return Response(content=str(fallback), media_type="application/xml")


# ──────────────────────────────────────────────
# TWILIO WEBHOOK: STATUS CALLBACK
# ──────────────────────────────────────────────

@app.post("/twilio/status")
async def twilio_status(request: Request):
    """Track call status changes (ringing, in-progress, completed, etc.)."""
    form = await request.form()
    call_sid = form.get("CallSid", "unknown")
    status = form.get("CallStatus", "unknown")
    duration = form.get("CallDuration", "0")

    print(f"[STATUS] Call status: {call_sid[-8:]} -> {status} (duration: {duration}s)")

    if status in ("completed", "busy", "failed", "no-answer"):
        # Clean up call state
        from backend.decision_engine import remove_call
        remove_call(call_sid)

    return JSONResponse({"status": "ok"})


# ──────────────────────────────────────────────
# WEBSOCKET: MEDIA STREAM
# ──────────────────────────────────────────────

@app.websocket("/twilio/media-stream")
async def media_stream_ws(websocket: WebSocket):
    """Bidirectional WebSocket for Twilio Media Streams."""
    await handle_media_stream(websocket)


# ──────────────────────────────────────────────
# API: CALL ME (Outbound call – Sahayak calls YOU)
# ──────────────────────────────────────────────

@app.post("/api/call-me")
async def call_me(request: Request):
    """
    Initiate an outbound call from Sahayak to the user's phone.
    This way the user doesn't need international calling pack.

    Body: {"phone": "+919876543210"}
    """
    body = await request.json()
    phone = body.get("phone", "").strip()

    if not phone:
        raise HTTPException(status_code=400, detail="'phone' is required (e.g. +919876543210)")

    # Ensure phone has country code
    if not phone.startswith("+"):
        phone = "+91" + phone  # default to India

    if not twilio_client:
        raise HTTPException(status_code=500, detail="Twilio credentials not configured in .env")

    try:
        call = twilio_client.calls.create(
            to=phone,
            from_=TWILIO_PHONE_NUMBER,
            url=f"{BASE_URL}/twilio/incoming",
            status_callback=f"{BASE_URL}/twilio/status",
            status_callback_event=["initiated", "ringing", "answered", "completed"],
            status_callback_method="POST",
        )
        print(f"[OUTBOUND] Calling {phone} -> Call SID: {call.sid}")
        return JSONResponse({
            "status": "calling",
            "message": f"Sahayak is calling {phone} now. Please pick up!",
            "call_sid": call.sid,
            "to": phone,
            "from": TWILIO_PHONE_NUMBER,
        })
    except Exception as e:
        print(f"[ERROR] Outbound call failed: {e}")
        raise HTTPException(status_code=500, detail=f"Call failed: {str(e)}")


# ──────────────────────────────────────────────
# API: TEST PIPELINE (no phone needed)
# ──────────────────────────────────────────────

@app.post("/api/test-pipeline")
async def test_pipeline(request: Request):
    """
    Test the full AI decision pipeline with text input.

    Body: {"text": "...", "call_sid": "test-123", "language": "kannada"}
    """
    body = await request.json()
    text = body.get("text", "")
    call_sid = body.get("call_sid", "test-" + os.urandom(4).hex())
    language = body.get("language", "kannada")

    if not text:
        raise HTTPException(status_code=400, detail="'text' is required")

    # Set language on call state
    call_state = get_or_create_call(call_sid)
    call_state.language = language

    result = await process_caller_input(call_sid, text)

    return JSONResponse({
        "response": result["response_text"],
        "action": result["action"],
        "call_state": {
            "call_sid": call_sid,
            "language": result["call_state"]["language"],
            "phase": result["call_state"]["current_phase"],
            "urgency": result["call_state"].get("analyses", [{}])[-1].get("urgency", 0) if result["call_state"].get("analyses") else 0,
            "confidence": result["call_state"].get("analyses", [{}])[-1].get("confidence", 0) if result["call_state"].get("analyses") else 0,
            "sentiment": result["call_state"].get("analyses", [{}])[-1].get("sentiment", "unknown") if result["call_state"].get("analyses") else "unknown",
            "transcript_length": len(result["call_state"].get("transcript", [])),
            "outcome": result["call_state"].get("outcome"),
        },
    })


# ──────────────────────────────────────────────
# API: DASHBOARD ENDPOINTS
# ──────────────────────────────────────────────

@app.get("/api/active-calls")
async def api_active_calls():
    """Get all currently active calls (in-memory)."""
    calls = []
    for sid, state in active_calls.items():
        calls.append({
            "call_sid": state.call_sid,
            "caller_number": state.caller_number,
            "language": state.language,
            "phase": state.current_phase,
            "ai_summary": state.ai_summary,
            "transcript_count": len(state.transcript),
            "outcome": state.outcome.value if state.outcome else None,
        })
    return JSONResponse({"active_calls": calls, "count": len(calls)})


@app.get("/api/call-logs")
async def api_call_logs():
    """Get recent call logs from Supabase."""
    try:
        logs = db.get_recent_calls(limit=50)
        return JSONResponse({"call_logs": logs, "count": len(logs)})
    except Exception as e:
        return JSONResponse({"call_logs": [], "count": 0, "error": str(e)})


@app.get("/api/agents")
async def api_agents():
    """Get all agents."""
    try:
        agents = db.get_all_agents()
        return JSONResponse({"agents": agents, "count": len(agents)})
    except Exception as e:
        return JSONResponse({"agents": [], "count": 0, "error": str(e)})


@app.post("/api/agent/toggle")
async def api_toggle_agent(request: Request):
    """Toggle agent availability."""
    body = await request.json()
    agent_id = body.get("agent_id")
    available = body.get("available")

    if not agent_id or available is None:
        raise HTTPException(status_code=400, detail="agent_id and available required")

    result = db.update_agent_availability(agent_id, available)
    return JSONResponse({"status": "ok", "agent": result})


@app.get("/api/complaints")
async def api_complaints():
    """Get recent complaints."""
    try:
        complaints = db.get_complaints(limit=50)
        return JSONResponse({"complaints": complaints, "count": len(complaints)})
    except Exception as e:
        return JSONResponse({"complaints": [], "count": 0, "error": str(e)})


@app.get("/api/resolved-cases")
async def api_resolved_cases():
    """Get the knowledge base of resolved cases."""
    try:
        cases = db.get_all_resolved_cases(limit=100)
        return JSONResponse({"cases": cases, "count": len(cases)})
    except Exception as e:
        return JSONResponse({"cases": [], "count": 0, "error": str(e)})


# ──────────────────────────────────────────────
# HEALTH CHECK
# ──────────────────────────────────────────────

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return JSONResponse({
        "status": "healthy",
        "service": "Sahayak 1092",
        "version": "1.0.0",
        "active_calls": len(active_calls),
    })


@app.get("/")
async def root():
    """Root endpoint with service info."""
    return JSONResponse({
        "service": "Sahayak 1092",
        "tagline": "Every Voice Heard. Every Call Resolved. Every Second Counts.",
        "version": "1.0.0",
        "endpoints": {
            "incoming_call": "POST /twilio/incoming",
            "media_stream": "WS /twilio/media-stream",
            "test_pipeline": "POST /api/test-pipeline",
            "active_calls": "GET /api/active-calls",
            "call_logs": "GET /api/call-logs",
            "agents": "GET /api/agents",
            "complaints": "GET /api/complaints",
            "resolved_cases": "GET /api/resolved-cases",
            "health": "GET /health",
        },
    })


# ──────────────────────────────────────────────
# RUN
# ──────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("backend.main:app", host=host, port=port, reload=True)

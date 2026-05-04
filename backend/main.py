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
import datetime as dt
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

from backend.api.health import build_health_payload
from backend.config import get_settings
from backend.media_stream import handle_media_stream
from backend.decision_engine import (
    get_or_create_call,
    process_caller_input,
)
from backend.intelligence.similarity import deterministic_seed_cases
from backend.persistence.complaints import get_complaint_registry
from backend.persistence.repository import get_call_repository
from backend.routing.queue_manager import get_queue_manager
from backend.routing.transfer_service import TransferRequest, get_transfer_service
from backend import supabase_client as db

load_dotenv()
settings = get_settings()
call_repository = get_call_repository()
complaint_registry = get_complaint_registry()
queue_manager = get_queue_manager()
transfer_service = get_transfer_service()

BASE_URL = settings.base_url
TWILIO_PHONE_NUMBER = settings.twilio_phone_number
TWILIO_ACCOUNT_SID = settings.twilio_account_sid
TWILIO_AUTH_TOKEN = settings.twilio_auth_token

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
    title=settings.app_name,
    description="AI-first voice-to-voice system for India's 1092 emergency helpline",
    version=settings.app_version,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
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
        print("[CALL] INCOMING CALL")
        print(f"   From     : {caller}")
        print(f"   To       : {called}")
        print(f"   CallSid  : {call_sid}")
        print(f"{'='*60}\n")

        # Build TwiML — Connect to bidirectional Media Stream
        response = VoiceResponse()
        response.pause(length=1)

        ws_url = settings.ws_base_url
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
        "analysis": result.get("analysis"),
        "similarity": result.get("similarity"),
        "call_state": {
            "call_sid": call_sid,
            "language": result["call_state"]["language"],
            "phase": result["call_state"]["current_phase"],
            "urgency": result["call_state"].get("analyses", [{}])[-1].get("urgency", 0) if result["call_state"].get("analyses") else 0,
            "confidence": result["call_state"].get("analyses", [{}])[-1].get("confidence", 0) if result["call_state"].get("analyses") else 0,
            "sentiment": result["call_state"].get("analyses", [{}])[-1].get("sentiment", "unknown") if result["call_state"].get("analyses") else "unknown",
            "transcript_length": len(result["call_state"].get("transcript", [])),
            "outcome": result["call_state"].get("outcome"),
            "complaint_registered": result["call_state"].get("complaint_registered"),
            "complaint_reference_id": result["call_state"].get("complaint_reference_id"),
            "matched_case_id": result["call_state"].get("matched_case_id"),
            "similarity_score": result["call_state"].get("similarity_score"),
            "similarity_source": result["call_state"].get("similarity_source"),
            "adapted_resolution": result["call_state"].get("adapted_resolution"),
            "similar_case": result["call_state"].get("similar_case"),
            "agent_id": result["call_state"].get("agent_id"),
            "handover_context": result["call_state"].get("handover_context"),
            "routing_score_breakdown": result["call_state"].get("routing_score_breakdown"),
            "officer_first_sentence": result["call_state"].get("officer_first_sentence"),
            "transfer_status": result["call_state"].get("transfer_status"),
            "transfer_mode": result["call_state"].get("transfer_mode"),
            "queue_entry_id": result["call_state"].get("queue_entry_id"),
            "queue_status": result["call_state"].get("queue_status"),
            "queue_position": result["call_state"].get("queue_position"),
            "queue_priority_score": result["call_state"].get("queue_priority_score"),
            "queue_estimated_wait_sec": result["call_state"].get("queue_estimated_wait_sec"),
            "queue_service_target": result["call_state"].get("queue_service_target"),
            "high_help_alert_at": result["call_state"].get("high_help_alert_at"),
        },
    })


# ──────────────────────────────────────────────
# API: DASHBOARD ENDPOINTS
# ──────────────────────────────────────────────

@app.get("/api/active-calls")
async def api_active_calls():
    """Get all currently active calls from live repository state."""
    calls = call_repository.fetch_active_calls()
    return JSONResponse({"active_calls": calls, "count": len(calls)})


@app.get("/api/call-logs")
async def api_call_logs():
    """Get recent call logs from repository/Supabase."""
    try:
        logs = call_repository.fetch_recent_calls(limit=50)
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


def _agent_from_context_or_db(agent_id: str, handover_context: dict) -> dict | None:
    selected = handover_context.get("selected_agent") or {}
    if str(selected.get("id") or "") == str(agent_id):
        return selected
    try:
        agent = db.get_agent_by_id(agent_id)
        if agent:
            return agent
    except Exception:
        pass
    for ranked in handover_context.get("ranked_agents") or []:
        if str(ranked.get("agent_id") or "") == str(agent_id):
            return {
                "id": ranked.get("agent_id"),
                "name": ranked.get("name"),
            }
    return None


@app.post("/api/handover/{call_sid}/accept")
async def api_accept_handover(call_sid: str, request: Request):
    """Officer accepts a warm handover and starts mock/Twilio transfer."""
    body = await request.json()
    agent_id = str(body.get("agent_id") or "").strip()
    notes = str(body.get("notes") or "").strip()
    if not agent_id:
        raise HTTPException(status_code=400, detail="'agent_id' is required")

    stored_state = call_repository.get_call_state(call_sid)
    if not stored_state:
        raise HTTPException(status_code=404, detail="Call not found")
    call_state = get_or_create_call(call_sid)
    if call_state.current_phase != "handover_pending":
        raise HTTPException(status_code=409, detail="Call is not waiting for handover acceptance")

    handover_context = call_state.handover_context or {}
    agent = _agent_from_context_or_db(agent_id, handover_context)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found for this handover")

    call_state.handover_accepted_by = agent_id
    call_state.handover_accepted_at = dt.datetime.now(dt.UTC).isoformat()
    call_state.transfer_status = "accepted"
    call_state.transfer_mode = settings.transfer_mode
    call_repository.update_call_state(call_state)
    call_repository.append_call_event(
        call_sid=call_sid,
        event_type="handover_accepted",
        payload={"agent_id": agent_id, "notes": notes},
        call_state=call_state,
    )

    transfer_result = transfer_service.accept_handover(
        TransferRequest(
            call_sid=call_sid,
            agent=agent,
            handover_context=handover_context,
            notes=notes,
        )
    )
    call_state.transfer_status = transfer_result.status
    call_state.transfer_mode = transfer_result.mode
    call_repository.update_call_state(call_state)
    call_repository.append_call_event(
        call_sid=call_sid,
        event_type="transfer_initiated",
        payload=transfer_result.as_dict(),
        call_state=call_state,
    )
    call_repository.append_call_event(
        call_sid=call_sid,
        event_type="transfer_completed" if transfer_result.success else "transfer_failed",
        payload=transfer_result.as_dict(),
        call_state=call_state,
    )
    if transfer_result.success:
        try:
            db.increment_agent_load(agent_id)
        except Exception:
            pass

    return JSONResponse(
        {
            "status": "ok" if transfer_result.success else "failed",
            "call_sid": call_sid,
            "agent": agent,
            "handover_context": handover_context,
            "transfer": transfer_result.as_dict(),
        }
    )


@app.get("/api/complaints")
async def api_complaints(call_sid: str | None = None):
    """Get recent structured complaints/actions through the registry facade."""
    try:
        complaints = complaint_registry.list_complaints(limit=50, call_sid=call_sid)
        return JSONResponse({"complaints": complaints, "count": len(complaints)})
    except Exception as e:
        return JSONResponse({"complaints": [], "count": 0, "error": str(e)})


@app.get("/api/complaints/{reference_id}/timeline")
async def api_complaint_timeline(reference_id: str):
    """Get complaint timeline events for a citizen-facing reference ID."""
    complaint = complaint_registry.get_by_reference(reference_id)
    timeline = complaint_registry.get_timeline(reference_id=reference_id, limit=100)
    return JSONResponse(
        {
            "reference_id": reference_id,
            "complaint": complaint,
            "timeline": timeline,
            "count": len(timeline),
        }
    )


@app.get("/api/resolved-cases")
async def api_resolved_cases():
    """Get the knowledge base of resolved cases."""
    try:
        cases = db.get_all_resolved_cases(limit=100)
        if not cases and settings.demo_mode:
            cases = [
                {key: value for key, value in case.items() if key != "embedding"}
                for case in deterministic_seed_cases()
            ]
        return JSONResponse({"cases": cases, "count": len(cases)})
    except Exception as e:
        if settings.demo_mode:
            cases = [
                {key: value for key, value in case.items() if key != "embedding"}
                for case in deterministic_seed_cases()
            ]
            return JSONResponse({"cases": cases, "count": len(cases), "fallback": "demo_seed"})
        return JSONResponse({"cases": [], "count": 0, "error": str(e)})


@app.get("/api/call-transcript/{call_sid}")
async def api_call_transcript(call_sid: str):
    """Get the transcript for a call from live state or durable logs."""
    transcript = call_repository.fetch_call_transcript(call_sid)
    return JSONResponse({"call_sid": call_sid, "transcript": transcript, "count": len(transcript)})


@app.get("/api/call-events")
async def api_call_events(call_sid: str | None = None, limit: int = 100):
    """Get audit events for one call or recent events across calls."""
    events = call_repository.fetch_call_events(call_sid=call_sid, limit=limit)
    return JSONResponse({"events": events, "count": len(events)})


@app.get("/api/queue")
async def api_queue(include_inactive: bool = False, limit: int = 50):
    """Get current priority queue entries."""
    entries = queue_manager.list_entries(include_inactive=include_inactive, limit=limit)
    return JSONResponse(
        {
            "queue": entries,
            "count": len(entries),
            "high_help_alert_timeout_sec": queue_manager.queue_timeout_sec(),
            "demo_mode": settings.demo_mode,
        }
    )


@app.get("/api/queue/{call_sid}")
async def api_queue_entry(call_sid: str):
    """Get one priority queue entry by call SID."""
    entry = queue_manager.get_entry(call_sid)
    if not entry:
        raise HTTPException(status_code=404, detail="Queue entry not found")
    return JSONResponse({"queue_entry": entry.as_dict()})


# ──────────────────────────────────────────────
# HEALTH CHECK
# ──────────────────────────────────────────────

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return JSONResponse(
        build_health_payload(
            active_calls=len(call_repository.fetch_active_calls()),
            persistence=call_repository.health_check(),
        )
    )


@app.get("/")
async def root():
    """Root endpoint with service info."""
    return JSONResponse({
        "service": settings.app_name,
        "tagline": "Every Voice Heard. Every Call Resolved. Every Second Counts.",
        "version": settings.app_version,
        "endpoints": {
            "incoming_call": "POST /twilio/incoming",
            "media_stream": "WS /twilio/media-stream",
            "test_pipeline": "POST /api/test-pipeline",
            "active_calls": "GET /api/active-calls",
            "call_logs": "GET /api/call-logs",
            "call_transcript": "GET /api/call-transcript/{call_sid}",
            "call_events": "GET /api/call-events?call_sid=...",
            "queue": "GET /api/queue",
            "queue_entry": "GET /api/queue/{call_sid}",
            "agents": "GET /api/agents",
            "accept_handover": "POST /api/handover/{call_sid}/accept",
            "complaints": "GET /api/complaints",
            "complaint_timeline": "GET /api/complaints/{reference_id}/timeline",
            "resolved_cases": "GET /api/resolved-cases",
            "health": "GET /health",
        },
    })


# ──────────────────────────────────────────────
# RUN
# ──────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host=settings.host, port=settings.port, reload=settings.debug)

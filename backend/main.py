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
import time
from contextlib import asynccontextmanager
from typing import Any
from uuid import uuid4

# Fix Windows console encoding for Unicode
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from fastapi import FastAPI, Request, WebSocket, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from twilio.twiml.voice_response import VoiceResponse, Connect, Stream
from twilio.rest import Client as TwilioClient
from twilio.base.exceptions import TwilioRestException

from backend.agent import get_sahayak_agent
from backend.api.health import build_health_payload
from backend.config import get_settings
from backend.media_stream import handle_media_stream
from backend.decision_engine import (
    get_or_create_call,
)
from backend.intelligence.schemas import CallAnalysis
from backend.intelligence.similarity import (
    deterministic_seed_cases,
    generate_case_embedding,
    serializable_embedding,
    urgency_band,
)
from backend.persistence.complaints import get_complaint_registry
from backend.persistence.repository import get_call_repository, state_to_dict
from backend.routing.queue_manager import get_queue_manager
from backend.security import (
    authorize_dashboard_request,
    client_ip,
    json_log,
    rate_limiter,
    request_id_from,
    validate_twilio_request,
)
from backend.routing.transfer_service import TransferRequest, get_transfer_service
from backend import supabase_client as db

load_dotenv()
settings = get_settings()
call_repository = get_call_repository()
complaint_registry = get_complaint_registry()
queue_manager = get_queue_manager()
transfer_service = get_transfer_service()
sahayak_agent = get_sahayak_agent()
local_learned_cases: list[dict[str, Any]] = []

BASE_URL = settings.base_url
TWILIO_PHONE_NUMBER = settings.twilio_phone_number
TWILIO_ACCOUNT_SID = settings.twilio_account_sid
TWILIO_AUTH_TOKEN = settings.twilio_auth_token

# Twilio REST client for outbound calls
twilio_client = None
if TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN:
    twilio_client = TwilioClient(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)


def _twilio_outbound_error_detail(exc: Exception) -> str:
    """Return a safe, actionable Twilio error for dashboard users."""

    if isinstance(exc, TwilioRestException):
        code = getattr(exc, "code", None)
        message = str(getattr(exc, "msg", "") or exc).strip()
        if code == 21608:
            return (
                "Twilio trial accounts can call only verified recipient numbers. "
                "Verify this phone number in Twilio, or upgrade the account."
            )
        if code == 21408:
            return (
                "Twilio geo permissions block calls to this country/region. "
                "Enable the destination country in Twilio Voice Geo Permissions."
            )
        if code == 21211:
            return "The destination phone number is invalid. Use E.164 format, for example +919876543210."
        if code == 21606:
            return "The configured Twilio caller number cannot make outbound voice calls."
        if code in {20003, 20005}:
            return "Twilio authentication/account status failed. Check TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN."
        if message:
            return f"Twilio rejected the call: {message}"
    return "Twilio rejected the outbound call. Check trial verification, geo permissions, balance, and number format."


# ── Lifespan ─────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown tasks."""
    json_log(
        "app_start",
        base_url=BASE_URL,
        twilio_phone_number=TWILIO_PHONE_NUMBER,
        environment=settings.environment,
        demo_mode=settings.demo_mode,
    )

    # Seed demo data
    try:
        await db.seed_demo_data()
    except Exception as exc:
        json_log("seed_skipped", error=str(exc))

    yield  # app running

    json_log("app_stop")


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


def _safe_error_response(
    request: Request,
    *,
    status_code: int,
    code: str,
    detail: str,
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", request_id_from(request, settings))
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": detail,
                "request_id": request_id,
            }
        },
        headers={settings.request_id_header: request_id},
    )


@app.middleware("http")
async def security_middleware(request: Request, call_next):
    """Attach request IDs, rate-limit, authenticate dashboard APIs, and log safely."""

    started_at = time.perf_counter()
    request_id = request_id_from(request, settings)
    request.state.request_id = request_id
    path = request.url.path
    method = request.method.upper()
    auth_decision = authorize_dashboard_request(request, settings)
    if not auth_decision.allowed:
        json_log(
            "auth_rejected",
            request_id=request_id,
            method=method,
            path=path,
            role=auth_decision.role,
            client_ip=client_ip(request),
        )
        return _safe_error_response(
            request,
            status_code=auth_decision.status_code,
            code="forbidden" if auth_decision.status_code == 403 else "unauthorized",
            detail=auth_decision.detail,
        )

    if settings.rate_limit_enabled:
        limit = (
            settings.rate_limit_per_minute
            if method in {"GET", "HEAD", "OPTIONS"}
            else settings.mutation_rate_limit_per_minute
        )
        allowed, remaining = rate_limiter.check(
            f"{client_ip(request)}:{method}:{path}",
            limit=limit,
        )
        if not allowed:
            json_log(
                "rate_limited",
                request_id=request_id,
                method=method,
                path=path,
                role=auth_decision.role,
                client_ip=client_ip(request),
            )
            return _safe_error_response(
                request,
                status_code=429,
                code="rate_limited",
                detail="Too many requests. Please retry shortly.",
            )
    else:
        remaining = -1

    response = await call_next(request)
    duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
    response.headers[settings.request_id_header] = request_id
    if remaining >= 0:
        response.headers["X-RateLimit-Remaining"] = str(remaining)
    json_log(
        "http_request",
        request_id=request_id,
        method=method,
        path=path,
        status_code=response.status_code,
        role=auth_decision.role,
        client_ip=client_ip(request),
        duration_ms=duration_ms,
    )
    return response


@app.exception_handler(HTTPException)
async def safe_http_exception_handler(request: Request, exc: HTTPException):
    detail = str(exc.detail) if exc.detail else "Request failed"
    return _safe_error_response(
        request,
        status_code=exc.status_code,
        code="http_error",
        detail=detail,
    )


@app.exception_handler(RequestValidationError)
async def safe_validation_exception_handler(request: Request, exc: RequestValidationError):
    return _safe_error_response(
        request,
        status_code=422,
        code="validation_error",
        detail="Invalid request payload",
    )


@app.exception_handler(Exception)
async def safe_unhandled_exception_handler(request: Request, exc: Exception):
    json_log(
        "unhandled_exception",
        request_id=getattr(request.state, "request_id", ""),
        path=request.url.path,
        error=str(exc),
    )
    return _safe_error_response(
        request,
        status_code=500,
        code="internal_error",
        detail="Internal server error",
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
    form = await request.form()
    if not validate_twilio_request(request, form, settings):
        raise HTTPException(status_code=403, detail="Invalid Twilio signature")

    try:
        call_sid = form.get("CallSid", "unknown")
        caller = form.get("From", "unknown")
        called = form.get("To", TWILIO_PHONE_NUMBER)

        json_log(
            "incoming_call",
            request_id=getattr(request.state, "request_id", ""),
            caller_number=caller,
            called_number=called,
            call_sid=call_sid,
        )

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
        json_log(
            "twiml_generated",
            request_id=getattr(request.state, "request_id", ""),
            call_sid=call_sid,
        )
        return Response(content=twiml, media_type="application/xml")

    except Exception as exc:
        json_log(
            "incoming_call_failed",
            request_id=getattr(request.state, "request_id", ""),
            error=str(exc),
        )
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
    if not validate_twilio_request(request, form, settings):
        raise HTTPException(status_code=403, detail="Invalid Twilio signature")
    call_sid = form.get("CallSid", "unknown")
    status = form.get("CallStatus", "unknown")
    duration = form.get("CallDuration", "0")

    json_log(
        "call_status",
        request_id=getattr(request.state, "request_id", ""),
        call_sid=call_sid,
        status=status,
        duration=duration,
    )

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
        json_log(
            "outbound_call_started",
            request_id=getattr(request.state, "request_id", ""),
            phone=phone,
            call_sid=call.sid,
        )
        return JSONResponse({
            "status": "calling",
            "message": f"Sahayak is calling {phone} now. Please pick up!",
            "call_sid": call.sid,
            "to": phone,
            "from": TWILIO_PHONE_NUMBER,
        })
    except Exception as exc:
        detail = _twilio_outbound_error_detail(exc)
        json_log(
            "outbound_call_failed",
            request_id=getattr(request.state, "request_id", ""),
            phone=phone,
            error=detail,
        )
        raise HTTPException(status_code=500, detail=detail)


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

    result = await sahayak_agent.handle_text_turn(
        call_sid=call_sid,
        text=text,
        language=language,
        channel="api_test",
        metadata={"endpoint": "/api/test-pipeline"},
    )

    return JSONResponse({
        "response": result["response_text"],
        "action": result["action"],
        "analysis": result.get("analysis"),
        "similarity": result.get("similarity"),
        "agent_trace": result.get("agent_trace"),
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


@app.get("/api/agent/tools")
async def api_agent_tools():
    """Return the bounded tool registry used by the Sahayak agent."""
    return JSONResponse(
        {
            "agent": "sahayak_1092",
            "agent_type": "bounded_emergency_operations_agent",
            "tools": sahayak_agent.tool_specs(),
        }
    )


@app.get("/api/agent/traces")
async def api_agent_traces(call_sid: str | None = None, limit: int = 20):
    """Return recent agent turn traces from the call-event audit log."""
    events = call_repository.fetch_call_events(call_sid=call_sid, limit=max(limit * 5, limit))
    traces = [
        event
        for event in events
        if event.get("event_type") == "agent_turn_completed"
    ][:limit]
    return JSONResponse({"agent_traces": traces, "count": len(traces)})


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
    except Exception:
        return JSONResponse({"call_logs": [], "count": 0, "error": "call_logs_unavailable"})


@app.get("/api/agents")
async def api_agents():
    """Get all agents."""
    try:
        agents = db.get_all_agents()
        return JSONResponse({"agents": agents, "count": len(agents)})
    except Exception:
        return JSONResponse({"agents": [], "count": 0, "error": "agents_unavailable"})


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


def _latest_analysis_payload(call_state) -> dict[str, Any]:
    if call_state.analyses:
        return dict(call_state.analyses[-1])
    return {}


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _case_for_response(case: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in case.items() if key != "embedding"}


@app.post("/api/calls/{call_sid}/corrections")
async def api_apply_call_corrections(call_sid: str, request: Request):
    """Apply officer corrections to AI output and store an audit event."""
    body = await request.json()
    call_state = call_repository.get_call_state(call_sid)
    if not call_state:
        raise HTTPException(status_code=404, detail="Call not found")

    latest = _latest_analysis_payload(call_state)
    previous = {
        "category": latest.get("category"),
        "urgency": latest.get("urgency"),
        "summary": call_state.ai_summary,
        "resolution": call_state.resolution,
    }
    category = str(body.get("category") or latest.get("category") or "general").strip()
    urgency = _optional_float(body.get("urgency"))
    if urgency is None:
        urgency = _optional_float(latest.get("urgency")) or 0.5
    summary = str(body.get("summary") or call_state.ai_summary or latest.get("summary") or "").strip()
    resolution = str(body.get("resolution") or call_state.resolution or "").strip()
    notes = str(body.get("notes") or "").strip()
    corrected_by = str(body.get("corrected_by") or body.get("agent_id") or "").strip()

    corrected_analysis = CallAnalysis(
        language=call_state.language or latest.get("language") or "english",
        dialect=call_state.dialect or latest.get("dialect") or "",
        sentiment=latest.get("sentiment") or "calm",
        urgency=urgency,
        confidence=_optional_float(latest.get("confidence")) or 0.9,
        category=category,
        summary=summary,
        raw_text=latest.get("raw_text") or "",
    )
    call_state.language = corrected_analysis.language
    call_state.dialect = corrected_analysis.dialect
    call_state.ai_summary = summary
    call_state.resolution = resolution
    if call_state.analyses:
        call_state.analyses[-1] = corrected_analysis.as_event_payload()
    else:
        call_state.analyses.append(corrected_analysis.as_event_payload())

    call_repository.update_call_state(call_state, analysis=corrected_analysis)
    event = call_repository.append_call_event(
        call_sid=call_sid,
        event_type="ai_correction_applied",
        payload={
            "previous": previous,
            "corrected": {
                "category": corrected_analysis.category,
                "urgency": corrected_analysis.urgency,
                "summary": summary,
                "resolution": resolution,
            },
            "notes": notes,
            "corrected_by": corrected_by,
        },
        call_state=call_state,
        analysis=corrected_analysis,
    )
    return JSONResponse(
        {
            "status": "ok",
            "call_sid": call_sid,
            "call_state": state_to_dict(call_state),
            "event": event,
        }
    )


@app.post("/api/resolved-cases/from-call")
async def api_add_resolved_case_from_call(request: Request):
    """Add a corrected human resolution to the Smart Similarity knowledge base."""
    body = await request.json()
    call_sid = str(body.get("call_sid") or "").strip()
    call_state = call_repository.get_call_state(call_sid) if call_sid else None
    latest = _latest_analysis_payload(call_state) if call_state else {}

    summary = str(
        body.get("summary")
        or (call_state.ai_summary if call_state else "")
        or latest.get("summary")
        or ""
    ).strip()
    resolution = str(
        body.get("resolution")
        or (call_state.resolution if call_state else "")
        or (call_state.adapted_resolution if call_state else "")
        or ""
    ).strip()
    if not summary or not resolution:
        raise HTTPException(status_code=400, detail="summary and resolution are required")

    urgency = _optional_float(body.get("urgency"))
    if urgency is None:
        urgency = _optional_float(latest.get("urgency")) or 0.5
    category = str(body.get("category") or latest.get("category") or "general").strip()
    language = str(
        body.get("language")
        or (call_state.language if call_state else "")
        or latest.get("language")
        or "english"
    ).strip()
    dialect = str(
        body.get("dialect")
        or (call_state.dialect if call_state else "")
        or latest.get("dialect")
        or ""
    ).strip()
    tags = body.get("tags") or [category, language, urgency_band(urgency)]
    if isinstance(tags, str):
        tags = [item.strip() for item in tags.split(",") if item.strip()]

    case = {
        "summary": summary,
        "category": category,
        "language": language,
        "dialect": dialect,
        "urgency_band": str(body.get("urgency_band") or urgency_band(urgency)),
        "resolution": resolution,
        "tags": tags,
        "source_call_sid": call_sid or None,
    }
    embedding = serializable_embedding(await generate_case_embedding(case))
    inserted = {}
    source = "local_fallback"
    if settings.supabase_configured:
        try:
            inserted = db.insert_resolved_case(**case, embedding=embedding)
            if inserted:
                source = "supabase"
        except Exception:
            inserted = {}

    if not inserted:
        inserted = {
            "id": f"local-learned-{uuid4()}",
            **case,
            "created_at": dt.datetime.now(dt.UTC).isoformat(),
        }
        local_learned_cases.insert(0, {**inserted, "embedding": embedding})

    analysis = CallAnalysis(
        language=language,
        dialect=dialect,
        category=category,
        urgency=urgency,
        confidence=_optional_float(latest.get("confidence")) or 0.9,
        summary=summary,
    )
    event = call_repository.append_call_event(
        call_sid=call_sid or str(inserted.get("id")),
        event_type="knowledge_base_case_added",
        payload={
            "case": _case_for_response(inserted),
            "source": source,
            "tags": tags,
        },
        call_state=call_state,
        analysis=analysis,
    )
    return JSONResponse(
        {
            "status": "ok",
            "source": source,
            "case": _case_for_response(inserted),
            "event": event,
        }
    )


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
    except Exception:
        return JSONResponse({"complaints": [], "count": 0, "error": "complaints_unavailable"})


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
        if local_learned_cases:
            learned = [_case_for_response(case) for case in local_learned_cases]
            cases = learned + cases
        return JSONResponse({"cases": cases, "count": len(cases)})
    except Exception:
        if settings.demo_mode:
            cases = [
                {key: value for key, value in case.items() if key != "embedding"}
                for case in deterministic_seed_cases()
            ]
            if local_learned_cases:
                learned = [_case_for_response(case) for case in local_learned_cases]
                cases = learned + cases
            return JSONResponse({"cases": cases, "count": len(cases), "fallback": "demo_seed"})
        return JSONResponse({"cases": [], "count": 0, "error": "resolved_cases_unavailable"})


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

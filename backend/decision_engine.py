"""
Sahayak 1092 – Decision Engine
================================
Handles ALL intelligence:
  • Language / dialect detection
  • Sentiment & urgency analysis
  • Confidence scoring
  • Confirmation Loop (Vachan)
  • Smart Similarity Detection against resolved cases
  • Agent routing with urgency-first scoring
  • Response generation in caller's language
"""

import time
from typing import Optional

from openai import AsyncOpenAI
from dotenv import load_dotenv

from backend.config import get_settings
from backend.intelligence.analyzer import analyze_call_utterance
from backend.intelligence.schemas import (
    CallAnalysis,
    CallOutcome,
    CallPhase,
    CallState,
    ConfirmationStatus,
    DecisionAction,
    DecisionResult,
    HandoverContext,
    SimilarityMatch,
)
from backend.intelligence.safety_rules import evaluate_handover
from backend.intelligence.similarity import (
    find_similar_resolved_case,
    generate_case_embedding,
    serializable_embedding,
    urgency_band,
)
from backend.persistence.complaints import get_complaint_registry
from backend.persistence.repository import get_call_repository, state_to_dict
from backend.routing.officer_router import (
    score_agent as _score_agent,
    select_best_agent,
)
from backend.routing.queue_manager import get_queue_manager
from backend import supabase_client as db

load_dotenv()
settings = get_settings()
call_repository = get_call_repository()
complaint_registry = get_complaint_registry()
queue_manager = get_queue_manager()

# ── LLM Client ──────────────────────────────────
client = AsyncOpenAI(
    api_key=settings.openai_api_key or "local-dev-missing-openai-key",
    base_url=settings.openai_base_url,  # Gemini: https://generativelanguage.googleapis.com/v1beta/openai/
    timeout=settings.llm_provider_timeout_sec,
)
MODEL = settings.llm_model

# ── In-memory active calls ──────────────────────
active_calls: dict[str, CallState] = {}


VACHAN_PHASES = {
    CallPhase.CONFIRMING.value,
    CallPhase.VACHAN_PENDING.value,
    CallPhase.VACHAN_PARTIAL.value,
}


def _decision_result(
    response_text: str,
    action: DecisionAction,
    call_state: CallState,
    analysis: CallAnalysis,
    *,
    agent: dict | None = None,
    handover_context: dict | None = None,
    similarity: SimilarityMatch | None = None,
    reason: str | None = None,
) -> dict:
    return DecisionResult(
        response_text=response_text,
        action=action,
        call_state=state_to_dict(call_state),
        analysis=analysis,
        agent=agent,
        handover_context=handover_context,
        similarity=similarity,
        reason=reason,
    ).as_response()


def _is_vachan_phase(call_state: CallState) -> bool:
    return call_state.current_phase in VACHAN_PHASES


def get_or_create_call(call_sid: str, caller_number: str = "") -> CallState:
    """Get existing call state or create new one."""
    if call_sid in active_calls:
        state = active_calls[call_sid]
        if caller_number and not state.caller_number:
            state.caller_number = caller_number
            call_repository.update_call_state(state)
        return state

    state = call_repository.get_call_state(call_sid)
    if state:
        if caller_number and not state.caller_number:
            state.caller_number = caller_number
            call_repository.update_call_state(state)
        active_calls[call_sid] = state
        return state

    active_calls[call_sid] = CallState(
        call_sid=call_sid,
        caller_number=caller_number,
    )
    call_repository.create_call_state(active_calls[call_sid])
    call_repository.append_call_event(
        call_sid=call_sid,
        event_type="call_started",
        payload={"caller_number": caller_number},
        call_state=active_calls[call_sid],
    )
    return active_calls[call_sid]


def remove_call(call_sid: str):
    """Clean up after call ends."""
    state = active_calls.get(call_sid) or call_repository.get_call_state(call_sid)
    if state:
        call_repository.append_call_event(
            call_sid=call_sid,
            event_type="call_completed",
            payload={"outcome": state.outcome.value if state.outcome else None},
            call_state=state,
        )
    active_calls.pop(call_sid, None)
    call_repository.remove_call_state(call_sid)


# ──────────────────────────────────────────────
# 1. ANALYSE UTTERANCE
# ──────────────────────────────────────────────

async def analyse_utterance(text: str, call_state: CallState) -> CallAnalysis:
    """Analyze a caller utterance through the configured structured analyzer."""

    analysis = await analyze_call_utterance(
        text=text,
        call_state=call_state,
        settings=settings,
        client=client,
    )
    call_state.language = analysis.language
    call_state.dialect = analysis.dialect
    call_state.analyses.append(analysis.as_event_payload())
    return analysis


# ──────────────────────────────────────────────
# 2. SMART SIMILARITY DETECTION
# ──────────────────────────────────────────────

async def find_similar_case(
    analysis: CallAnalysis,
    call_state: CallState,
) -> SimilarityMatch | None:
    """Retrieve a similar resolved case, then optionally adapt its resolution."""

    return await find_similar_resolved_case(
        analysis=analysis,
        call_state=call_state,
        settings=settings,
        llm_client=client,
    )


# ──────────────────────────────────────────────
# 3. GENERATE AI RESPONSE
# ──────────────────────────────────────────────

RESPONSE_SYSTEM_PROMPT = """You are Sahayak, the AI voice assistant for India's 1092 emergency helpline.

YOU ARE ON A LIVE CALL. Every word must be calm, clear, and action-oriented.

CORE RULES:
- Speak ONLY in the caller's language: {language}
- Keep responses to 2-3 sentences MAXIMUM. This is a voice call - brevity saves lives.
- NEVER ask more than ONE question at a time.
- For emergencies (accident/medical/fire/trapped): immediately confirm help is dispatched, then ask the ONE most urgent missing detail.
- NEVER say "Maybe I misunderstood" or "Please tell me what was wrong" for emergencies.
- Be warm but decisive. Match the caller's urgency level.
- If ambulance/police/fire is needed: say "I am dispatching [service] to you right now."

SITUATION:
Phase: {phase} | Category: {category} | Urgency: {urgency} | Sentiment: {sentiment}
Issue: {summary}

RESPONSE RULES BY PHASE:
- greeting/collecting_issue: Ask what help they need, ONE empathetic sentence.
- vachan_pending: Confirm your understanding, ask yes/no.
- resolved: Give reference number, say help is coming.
- handover/handover_pending: Say you are connecting them to an officer.
- queued: Say help is coming, offer IVR options (1=Police, 2=Ambulance, 3=Fire).
- For high urgency (>0.85): Lead with action first, question second."""


async def generate_response(call_state: CallState, analysis: CallAnalysis,
                            resolution: str = None) -> str:
    """Generate an empathetic, actionable response in the caller's language."""
    if not settings.openai_api_key:
        return _deterministic_response(call_state, analysis, resolution)

    lang = analysis.language or call_state.language
    is_emergency = analysis.urgency >= 0.85 and analysis.category in {
        "accident", "medical", "fire", "missing_person", "domestic"
    }

    phase_instructions = {
        "greeting": "Greet the caller warmly in their language and ask what emergency help they need.",
        "listening": "Acknowledge their situation with empathy. Ask the ONE most important question to help them.",
        "confirming": f"Restate your understanding and the proposed resolution. Ask for yes/no confirmation.\nProposed resolution: {resolution or 'pending'}",
        "collecting_issue": (
            "For emergencies: immediately confirm you are taking action. Ask for their location if not known. "
            "For non-emergencies: acknowledge and collect the issue in one calm, specific question."
        ),
        "clarifying": (
            "For emergencies: do NOT say 'maybe I misunderstood'. Instead, acknowledge you heard them "
            "and ask for the ONE missing detail needed to dispatch help (usually location)."
            "For non-emergencies: ask what was wrong or missing. Ask for only the correction."
        ),
        "vachan_pending": f"Restate your understanding clearly and the action being taken. Ask: Is this correct?\nAction: {resolution or call_state.resolution or 'dispatching help'}",
        "vachan_partial": (
            f"Ask only for the missing detail: {', '.join(call_state.pending_clarification_fields or ['location'])}. "
            "Keep it to ONE short sentence."
        ),
        "resolved": f"Confirm help is on the way or the complaint is registered. Give the reference number.\nResolution: {resolution or call_state.resolution}",
        "handover": "Say you are connecting them to a human officer now. Reassure them their details are passed on.",
        "handover_pending": "Say you are connecting them to a human officer now. Reassure them their details are passed on.",
        "queued": "Say all officers are busy but their call is prioritized. Offer: say 'police' for Police, 'ambulance' for Ambulance, 'fire' for Fire.",
    }

    instruction = phase_instructions.get(call_state.current_phase, "Respond helpfully and ask ONE clear question.")

    # For emergency: add an explicit directive at the top
    if is_emergency:
        instruction = (
            f"EMERGENCY — {analysis.category.upper()}. Urgency {analysis.urgency:.0%}.\n"
            f"Summary: {analysis.summary or analysis.raw_text}\n"
            f"{instruction}\n"
            "Lead with action/reassurance. If location is missing, ask for it NOW. "
            "Keep your response to 2 sentences max."
        )

    messages = [
        {"role": "system", "content": RESPONSE_SYSTEM_PROMPT.format(
            language=lang,
            phase=call_state.current_phase,
            summary=analysis.summary or call_state.ai_summary,
            category=analysis.category,
            sentiment=analysis.sentiment,
            urgency=f"{analysis.urgency:.2f}",
        )},
    ]

    # Add conversation history (fewer turns for speed in emergencies)
    history_turns = 4 if is_emergency else 8
    for t in call_state.transcript[-history_turns:]:
        role = "user" if t["role"] == "caller" else "assistant"
        messages.append({"role": role, "content": t["text"]})

    messages.append({"role": "user", "content": f"[INSTRUCTION: {instruction}]\nCaller said: \"{analysis.raw_text}\""})

    # Try primary model then fallbacks
    models_to_try = list(dict.fromkeys([MODEL] + list(settings.llm_model_fallbacks)))
    for model in models_to_try:
        try:
            resp = await client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.4,
                max_tokens=150,
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            err_str = str(e)
            if "404" in err_str or "NOT_FOUND" in err_str or "no longer available" in err_str.lower():
                continue  # try next model
            print(f"❌ Response generation error ({model}): {e}")
            break

    return _deterministic_response(call_state, analysis, resolution)



# ──────────────────────────────────────────────
# 4. AGENT ROUTING (Urgency-First + Language-Matched)
# ──────────────────────────────────────────────

def score_agent(agent: dict, call_state: CallState, analysis: CallAnalysis) -> float:
    """Compatibility wrapper around the production routing module."""
    return _score_agent(
        agent=agent,
        call_language=call_state.language,
        category=analysis.category,
        dialect=call_state.dialect or analysis.dialect,
        urgency=analysis.urgency,
    )


async def route_to_agent(call_state: CallState, analysis: CallAnalysis) -> Optional[dict]:
    """Find the best available agent based on scoring algorithm."""
    agents = db.get_available_agents(language=call_state.language)
    if not agents:
        agents = db.get_available_agents()  # fallback: any language

    if not agents:
        return None

    return select_best_agent(
        agents=agents,
        call_language=call_state.language,
        category=analysis.category,
        dialect=call_state.dialect or analysis.dialect,
        urgency=analysis.urgency,
    )


def _build_officer_first_sentence(
    agent: dict,
    call_state: CallState,
    analysis: CallAnalysis,
) -> str:
    """Create a calm first sentence so the officer does not start from zero."""

    officer_name = agent.get("name") or "the assigned officer"
    summary = call_state.ai_summary or analysis.summary or "your concern"
    return (
        f"Hello, I am {officer_name} from Sahayak 1092. "
        f"I have your {analysis.category} report: {summary}. "
        "I will continue from here, so you do not need to repeat everything."
    )


def _build_handover_context(
    *,
    call_state: CallState,
    analysis: CallAnalysis,
    route_result: dict,
    handover_reason: str,
) -> dict:
    agent = route_result["agent"]
    first_sentence = _build_officer_first_sentence(agent, call_state, analysis)
    return HandoverContext(
        call_sid=call_state.call_sid,
        caller_number=call_state.caller_number,
        transcript=call_state.transcript,
        ai_summary=call_state.ai_summary,
        sentiment=analysis.sentiment,
        urgency=analysis.urgency,
        confidence=analysis.confidence,
        language=analysis.language,
        dialect=call_state.dialect or analysis.dialect,
        category=analysis.category,
        handover_reason=handover_reason,
        selected_agent=agent,
        routing_score=route_result.get("score", 0.0),
        routing_score_breakdown=route_result.get("score_breakdown", {}),
        ranked_agents=route_result.get("ranked_agents", []),
        officer_first_sentence=first_sentence,
    ).as_event_payload()


# ──────────────────────────────────────────────
# 5. MASTER DECISION PIPELINE
# ──────────────────────────────────────────────

async def process_caller_input(call_sid: str, text: str, caller_number: str = "") -> dict:
    """
    Main pipeline: Receive caller text → analyse → decide → respond.

    Returns dict with:
      - response_text: what to say back
      - action: "continue" | "resolve" | "handover" | "queue" | "ivr_redirect"
      - call_state: current state
    """
    call_state = get_or_create_call(call_sid, caller_number)

    # Add caller utterance to transcript
    call_state.transcript.append({"role": "caller", "text": text})
    call_repository.update_call_state(call_state)
    call_repository.append_call_event(
        call_sid=call_sid,
        event_type="utterance_received",
        payload={"text": text},
        call_state=call_state,
    )

    # ── Step 1: Analyse ──
    analysis_started_at = time.perf_counter()
    analysis = await analyse_utterance(text, call_state)
    analysis_latency_ms = round((time.perf_counter() - analysis_started_at) * 1000, 2)
    call_state.ai_summary = analysis.summary
    _persist_call(call_state, analysis)
    call_repository.append_call_event(
        call_sid=call_sid,
        event_type="analysis_completed",
        payload={**analysis.as_event_payload(), "latency_ms": analysis_latency_ms},
        call_state=call_state,
        analysis=analysis,
    )

    # ── Step 2: Check deterministic handover conditions ──
    handover_decision = evaluate_handover(
        analysis=analysis,
        current_attempt_count=call_state.attempt_count,
        settings=settings,
    )
    call_state.attempt_count += handover_decision.attempt_increment

    if handover_decision.needs_handover:
        call_state.handover_reason = handover_decision.reason
        call_repository.append_call_event(
            call_sid=call_sid,
            event_type="handover_requested",
            payload={
                "reason": handover_decision.reason.value if handover_decision.reason else None,
                "explanation": handover_decision.explanation,
            },
            call_state=call_state,
            analysis=analysis,
        )
        route_result = await route_to_agent(call_state, analysis)

        if route_result:
            # Successful match → warm handover
            call_state.current_phase = CallPhase.HANDOVER_PENDING.value
            call_state.outcome = CallOutcome.HANDED_OVER
            call_state.agent_id = route_result["agent"]["id"]
            handover_reason = handover_decision.reason.value if handover_decision.reason else ""
            handover_context = _build_handover_context(
                call_state=call_state,
                analysis=analysis,
                route_result=route_result,
                handover_reason=handover_reason,
            )
            call_state.handover_context = handover_context
            call_state.routing_score_breakdown = route_result.get("score_breakdown", {})
            call_state.officer_first_sentence = handover_context["officer_first_sentence"]
            call_state.transfer_status = "awaiting_officer_acceptance"
            call_state.transfer_mode = settings.transfer_mode
            response = await generate_response(call_state, analysis)
            call_state.transcript.append({"role": "sahayak", "text": response})
            call_repository.append_call_event(
                call_sid=call_sid,
                event_type="officer_matched",
                payload={
                    "agent": route_result["agent"],
                    "score": route_result.get("score"),
                    "score_breakdown": route_result.get("score_breakdown"),
                    "ranked_agents": route_result.get("ranked_agents", []),
                    "reason": route_result.get("reason"),
                    "handover_context": handover_context,
                    "officer_first_sentence": call_state.officer_first_sentence,
                },
                call_state=call_state,
                analysis=analysis,
            )

            # Persist to DB
            _persist_call(call_state, analysis)

            return _decision_result(
                response,
                DecisionAction.HANDOVER,
                call_state,
                analysis,
                agent=route_result["agent"],
                handover_context=handover_context,
            )
        else:
            # No agent available → queue with IVR
            reason = handover_decision.reason.value if handover_decision.reason else ""
            queue_entry = queue_manager.enqueue_call(call_state, analysis, reason=reason)
            queue_manager.apply_to_call_state(call_state, queue_entry)
            call_state.current_phase = CallPhase.QUEUED.value
            call_state.outcome = CallOutcome.QUEUED
            call_state.queue_start_time = time.time()
            response = await generate_response(call_state, analysis)
            call_state.transcript.append({"role": "sahayak", "text": response})
            call_repository.append_call_event(
                call_sid=call_sid,
                event_type="queued",
                payload={
                    "reason": reason,
                    "queue_start_time": call_state.queue_start_time,
                    "queue": queue_entry.as_dict(),
                    "high_help_alert_timeout_sec": queue_manager.queue_timeout_sec(),
                },
                call_state=call_state,
                analysis=analysis,
            )
            call_repository.append_call_event(
                call_sid=call_sid,
                event_type="queue_updated",
                payload=queue_entry.as_dict(),
                call_state=call_state,
                analysis=analysis,
            )

            _persist_call(call_state, analysis)

            return _decision_result(
                response,
                DecisionAction.QUEUE,
                call_state,
                analysis,
                reason=reason,
            )

    # ── Step 3: Confirmation Loop (Vachan) ──
    if _is_vachan_phase(call_state):
        incoming_vachan_phase = call_state.current_phase
        confirmation_status = analysis.confirmation_status
        if analysis.is_confirmation is True:
            confirmation_status = ConfirmationStatus.YES.value
        elif analysis.is_confirmation is False:
            confirmation_status = ConfirmationStatus.NO.value

        if confirmation_status == ConfirmationStatus.YES.value:
            # Confirmed! → Resolve
            call_state.current_phase = CallPhase.RESOLVED.value
            call_state.outcome = CallOutcome.AI_RESOLVED
            call_repository.append_call_event(
                call_sid=call_sid,
                event_type="vachan_confirmed",
                payload={
                    "summary": call_state.ai_summary,
                    "resolution": call_state.resolution,
                    "corrections": call_state.vachan_corrections,
                },
                call_state=call_state,
                analysis=analysis,
            )

            # Register complaint
            final_category = (
                (call_state.similar_case or {}).get("category")
                or analysis.category
                or "general"
            )
            complaint = complaint_registry.register_ai_resolved_complaint(
                call_state=call_state,
                analysis=analysis,
                category=final_category,
                resolution=call_state.resolution,
            )
            call_state.complaint_registered = True
            call_state.complaint_reference_id = complaint.get("reference_id")
            call_repository.append_call_event(
                call_sid=call_sid,
                event_type="complaint_registered",
                payload={
                    "category": final_category,
                    "reference_id": complaint.get("reference_id"),
                    "complaint_id": complaint.get("id"),
                    "status": complaint.get("status"),
                    "location": complaint.get("location"),
                    "government_payload": complaint.get("government_payload"),
                },
                call_state=call_state,
                analysis=analysis,
            )
            call_repository.append_call_event(
                call_sid=call_sid,
                event_type="complaint_timeline_updated",
                payload={
                    "reference_id": complaint.get("reference_id"),
                    "events": ["complaint_registered", "government_payload_created"],
                },
                call_state=call_state,
                analysis=analysis,
            )
            try:
                db.update_call_log(
                    call_sid=call_sid,
                    complaint_reference_id=call_state.complaint_reference_id,
                )
            except Exception:
                pass

            # Add to knowledge base
            try:
                learned_case = {
                    "summary": call_state.ai_summary,
                    "category": final_category,
                    "language": call_state.language,
                    "dialect": call_state.dialect,
                    "urgency_band": urgency_band(analysis.urgency),
                    "resolution": call_state.resolution,
                    "tags": [final_category, "ai_resolved"],
                }
                embedding = await generate_case_embedding(learned_case)
                db.insert_resolved_case(
                    summary=call_state.ai_summary,
                    category=final_category,
                    language=call_state.language,
                    dialect=call_state.dialect,
                    urgency_band=learned_case["urgency_band"],
                    resolution=call_state.resolution,
                    tags=learned_case["tags"],
                    source_call_sid=call_sid,
                    embedding=serializable_embedding(embedding),
                )
            except Exception:
                pass

            response = await generate_response(call_state, analysis, call_state.resolution)
            call_state.transcript.append({"role": "sahayak", "text": response})
            _persist_call(call_state, analysis)

            return _decision_result(response, DecisionAction.RESOLVE, call_state, analysis)

        if confirmation_status == ConfirmationStatus.NO.value:
            # Not confirmed → ask what was wrong before taking any final action.
            call_state.current_phase = CallPhase.CLARIFYING.value
            call_state.attempt_count += 1
            call_state.pending_clarification_fields = analysis.missing_fields or ["description"]
            call_state.vachan_corrections.append(
                {
                    "status": ConfirmationStatus.NO.value,
                    "text": analysis.correction_text or analysis.raw_text,
                    "fields": call_state.pending_clarification_fields,
                }
            )
            call_repository.append_call_event(
                call_sid=call_sid,
                event_type="vachan_rejected",
                payload={
                    "text": analysis.correction_text or analysis.raw_text,
                    "fields": call_state.pending_clarification_fields,
                },
                call_state=call_state,
                analysis=analysis,
            )
            call_repository.append_call_event(
                call_sid=call_sid,
                event_type="vachan_correction_requested",
                payload={"fields": call_state.pending_clarification_fields},
                call_state=call_state,
                analysis=analysis,
            )
            response = await generate_response(call_state, analysis)
            call_state.transcript.append({"role": "sahayak", "text": response})
            _persist_call(call_state, analysis)
            return _decision_result(response, DecisionAction.CONTINUE, call_state, analysis)

        if confirmation_status == ConfirmationStatus.PARTIAL.value:
            correction = {
                "status": ConfirmationStatus.PARTIAL.value,
                "text": analysis.correction_text or analysis.raw_text,
                "fields": analysis.missing_fields or call_state.pending_clarification_fields or ["description"],
            }
            call_state.vachan_corrections.append(correction)
            call_state.pending_clarification_fields = correction["fields"]
            call_repository.append_call_event(
                call_sid=call_sid,
                event_type="vachan_partial",
                payload=correction,
                call_state=call_state,
                analysis=analysis,
            )

            if incoming_vachan_phase == CallPhase.VACHAN_PARTIAL.value:
                call_state.ai_summary = _apply_vachan_correction(call_state.ai_summary, correction)
                call_state.current_phase = CallPhase.VACHAN_PENDING.value
                call_state.vachan_prompt = _build_vachan_prompt(call_state)
                response = await generate_response(call_state, analysis, call_state.resolution)
                call_state.transcript.append({"role": "sahayak", "text": response})
                call_repository.append_call_event(
                    call_sid=call_sid,
                    event_type="vachan_requested",
                    payload={
                        "resolution": call_state.resolution,
                        "source": "partial_correction",
                        "summary": call_state.ai_summary,
                    },
                    call_state=call_state,
                    analysis=analysis,
                )
                _persist_call(call_state, analysis)
                return _decision_result(response, DecisionAction.CONTINUE, call_state, analysis)

            call_state.current_phase = CallPhase.VACHAN_PARTIAL.value
            call_repository.append_call_event(
                call_sid=call_sid,
                event_type="vachan_correction_requested",
                payload={"fields": call_state.pending_clarification_fields},
                call_state=call_state,
                analysis=analysis,
            )
            response = await generate_response(call_state, analysis)
            call_state.transcript.append({"role": "sahayak", "text": response})
            _persist_call(call_state, analysis)
            return _decision_result(response, DecisionAction.CONTINUE, call_state, analysis)

        call_repository.append_call_event(
            call_sid=call_sid,
            event_type="vachan_correction_requested",
            payload={"fields": ["yes_no_or_correction"], "reason": "confirmation_unclear"},
            call_state=call_state,
            analysis=analysis,
        )
        response = await generate_response(call_state, analysis, call_state.resolution)
        call_state.transcript.append({"role": "sahayak", "text": response})
        _persist_call(call_state, analysis)
        return _decision_result(response, DecisionAction.CONTINUE, call_state, analysis)

    # ── Step 4: Smart Similarity Detection ──
    autonomous_input_phases = {
        CallPhase.GREETING.value,
        CallPhase.LISTENING.value,
        CallPhase.COLLECTING_ISSUE.value,
        CallPhase.CLARIFYING.value,
    }
    if analysis.confidence >= 0.6 and call_state.current_phase in autonomous_input_phases:
        similarity_started_at = time.perf_counter()
        similar = await find_similar_case(analysis, call_state)
        similarity_latency_ms = round((time.perf_counter() - similarity_started_at) * 1000, 2)
        call_repository.append_call_event(
            call_sid=call_sid,
            event_type="similarity_search_completed",
            payload={
                "latency_ms": similarity_latency_ms,
                "matched": bool(similar),
                "retrieval_source": similar.retrieval_source if similar else None,
                "threshold": settings.similarity_match_threshold,
            },
            call_state=call_state,
            analysis=analysis,
        )
        if similar and similar.similarity_score >= settings.similarity_match_threshold:
            call_state.similar_case = similar.matched_case
            call_state.matched_case_id = similar.matched_case_id
            call_state.similarity_score = similar.similarity_score
            call_state.similarity_source = similar.retrieval_source
            call_state.adapted_resolution = similar.adapted_resolution
            call_state.resolution = similar.adapted_resolution
            call_state.current_phase = CallPhase.VACHAN_PENDING.value
            call_state.ai_summary = analysis.summary
            call_state.vachan_prompt = _build_vachan_prompt(call_state)
            call_repository.append_call_event(
                call_sid=call_sid,
                event_type="similarity_match_found",
                payload={**similar.as_event_payload(), "latency_ms": similarity_latency_ms},
                call_state=call_state,
                analysis=analysis,
            )

            response = await generate_response(call_state, analysis, similar.adapted_resolution)
            call_state.transcript.append({"role": "sahayak", "text": response})
            call_repository.append_call_event(
                call_sid=call_sid,
                event_type="vachan_requested",
                payload={
                    "resolution": similar.adapted_resolution,
                    "source": "similarity",
                    "matched_case_id": similar.matched_case_id,
                    "similarity_score": similar.similarity_score,
                    "similarity_source": similar.retrieval_source,
                },
                call_state=call_state,
                analysis=analysis,
            )
            _persist_call(call_state, analysis)

            return _decision_result(
                response,
                DecisionAction.CONTINUE,
                call_state,
                analysis,
                similarity=similar,
            )

    # ── Step 5: High confidence → AI takes ownership ──
    if analysis.confidence >= 0.7 and call_state.current_phase in autonomous_input_phases:
        # Generate resolution
        resolution = await _generate_resolution(analysis, call_state)
        call_state.resolution = resolution
        call_state.adapted_resolution = resolution
        call_state.current_phase = CallPhase.VACHAN_PENDING.value
        call_state.ai_summary = analysis.summary
        call_state.vachan_prompt = _build_vachan_prompt(call_state)

        response = await generate_response(call_state, analysis, resolution)
        call_state.transcript.append({"role": "sahayak", "text": response})
        call_repository.append_call_event(
            call_sid=call_sid,
            event_type="vachan_requested",
            payload={"resolution": resolution, "source": "generated"},
            call_state=call_state,
            analysis=analysis,
        )
        _persist_call(call_state, analysis)

        return _decision_result(response, DecisionAction.CONTINUE, call_state, analysis)

    # ── Step 6: Continue listening ──
    if call_state.current_phase in {CallPhase.GREETING.value, CallPhase.COLLECTING_ISSUE.value}:
        call_state.current_phase = CallPhase.CLARIFYING.value

    response = await generate_response(call_state, analysis)
    call_state.transcript.append({"role": "sahayak", "text": response})
    _persist_call(call_state, analysis)

    return _decision_result(response, DecisionAction.CONTINUE, call_state, analysis)


# ──────────────────────────────────────────────
# 6. GENERATE GREETING
# ──────────────────────────────────────────────

GREETING_TEMPLATES = {
    "hindi": "नमस्ते, सहायक 1092 से बात कर रहे हैं। मैं आपकी AI सहायक हूँ। आप अपनी समस्या बताइए, मैं तुरंत मदद करूँगी।",
    "kannada": "ನಮಸ್ಕಾರ, ಸಹಾಯಕ್ 1092 ಇಲ್ಲಿಂದ ಮಾತನಾಡುತ್ತಿದ್ದೇನೆ. ನಾನು ನಿಮ್ಮ AI ಸಹಾಯಕ. ನಿಮ್ಮ ಸಮಸ್ಯೆಯನ್ನು ಹೇಳಿ, ನಾನು ತಕ್ಷಣ ಸಹಾಯ ಮಾಡುತ್ತೇನೆ.",
    "english": "Hello, you have reached Sahayak 1092. I am your AI assistant. Please describe your situation and I will help you right away.",
    "telugu": "నమస్కారం, సహాయక్ 1092 నుండి మాట్లాడుతున్నాను. నేను మీ AI సహాయకురాలిని. మీ సమస్య చెప్పండి, నేను వెంటనే సహాయం చేస్తాను.",
    "tamil": "வணக்கம், சஹாயக் 1092 இல் இருந்து பேசுகிறேன். நான் உங்கள் AI உதவியாளர். உங்கள் பிரச்சினையை சொல்லுங்கள், உடனே உதவுகிறேன்.",
    "bengali": "নমস্কার, সহায়ক 1092 থেকে বলছি। আমি আপনার AI সহকারী। আপনার সমস্যা বলুন, আমি এখনই সাহায্য করব।",
    "marathi": "नमस्कार, सहायक 1092 मधून बोलत आहे. मी तुमची AI सहाय्यक आहे. तुमची समस्या सांगा, मी लगेच मदत करेन.",
    "gujarati": "નમસ્તે, સહાયક 1092 માંથી વાત કરી રહ્યાં છો. હું તમારી AI સહાયક છું. તમારી સમસ્યા જણાવો, હું તરત જ મદદ કરીશ.",
    "punjabi": "ਸਤਿ ਸ੍ਰੀ ਅਕਾਲ, ਸਹਾਇਕ 1092 ਤੋਂ ਬੋਲ ਰਹੀ ਹਾਂ। ਮੈਂ ਤੁਹਾਡੀ AI ਸਹਾਇਕ ਹਾਂ। ਆਪਣੀ ਸਮੱਸਿਆ ਦੱਸੋ, ਮੈਂ ਤੁਰੰਤ ਮਦਦ ਕਰਾਂਗੀ।",
    "malayalam": "നമസ്കാരം, സഹായക് 1092 ൽ നിന്ന് സംസാരിക്കുകയാണ്. ഞാൻ നിങ്ങളുടെ AI സഹായകയാണ്. നിങ്ങളുടെ പ്രശ്നം പറയൂ, ഞാൻ ഉടൻ സഹായിക്കാം.",
    "urdu": "آداب، سہایک 1092 سے بات ہو رہی ہے۔ میں آپ کی AI معاون ہوں۔ اپنا مسئلہ بتائیں، میں فوری مدد کروں گی۔",
    "odia": "ନମସ୍କାର, ସହାୟକ 1092 ରୁ କଥା ହେଉଛୁ। ମୁଁ ଆପଣଙ୍କ AI ସହାୟକ। ଆପଣଙ୍କ ସମସ୍ୟା କୁହନ୍ତୁ, ମୁଁ ତୁରନ୍ତ ସାହାଯ୍ୟ କରିବି।",
}


def get_greeting(language: str = "hindi") -> str:
    """Get the initial greeting in the caller's language. Defaults to Hindi."""
    return GREETING_TEMPLATES.get(language.lower(), GREETING_TEMPLATES["hindi"])


# ──────────────────────────────────────────────
# INTERNAL HELPERS
# ──────────────────────────────────────────────

RESOLUTION_SYSTEM_PROMPT = """You are Sahayak 1092's resolution engine.
Given a caller's issue, generate a practical, actionable resolution.
Include:
1. Immediate steps the caller should take
2. What action Sahayak is taking (e.g., registering FIR, dispatching patrol)
3. Any reference numbers or follow-up steps

Keep it concise (3-5 sentences). Respond in {language}.
Only output the resolution text, no JSON."""


def _build_vachan_prompt(call_state: CallState) -> str:
    """Build the exact understanding Sahayak is asking the citizen to verify."""

    summary = call_state.ai_summary or "your issue"
    resolution = call_state.resolution or call_state.adapted_resolution or "the next action"
    return (
        f"I understood this: {summary}. "
        f"Sahayak will do this: {resolution}. "
        "Is this correct? Please say yes, no, or tell me what is wrong."
    )


def _apply_vachan_correction(summary: str, correction: dict) -> str:
    """Keep corrections visible in state without pretending to fully re-parse them."""

    text = str(correction.get("text") or "").strip()
    fields = ", ".join(correction.get("fields") or ["description"])
    if not text:
        return summary
    base = summary or "Caller issue"
    return f"{base} Correction for {fields}: {text}"


async def _generate_resolution(analysis: CallAnalysis, call_state: CallState) -> str:
    """Generate a resolution for the caller's issue."""
    if not settings.openai_api_key:
        return _fallback_resolution(call_state, analysis)

    messages = [
        {"role": "system", "content": RESOLUTION_SYSTEM_PROMPT.format(language=analysis.language)},
        {"role": "user", "content": f"Category: {analysis.category}\nIssue: {analysis.summary}\nUrgency: {analysis.urgency}\nSentiment: {analysis.sentiment}"},
    ]
    models_to_try = list(dict.fromkeys([MODEL] + list(settings.llm_model_fallbacks)))
    for model in models_to_try:
        try:
            resp = await client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.4,
                max_tokens=250,
            )
            return resp.choices[0].message.content.strip()
        except Exception as exc:
            err_str = str(exc)
            if "404" in err_str or "NOT_FOUND" in err_str or "no longer available" in err_str.lower():
                continue
            break
    return _fallback_resolution(call_state, analysis)


def _fallback_resolution(call_state: CallState, analysis: CallAnalysis | None = None) -> str:
    ref = call_state.complaint_reference_id or f"SAH-{call_state.call_sid[-6:].upper()}"
    category = (analysis.category if analysis else None) or "general"
    lang = (analysis.language if analysis else None) or call_state.language or "hindi"

    if category == "accident":
        if lang == "hindi":
            return f"एम्बुलेंस और पुलिस को सूचित किया जा रहा है। संदर्भ: {ref}। कृपया फोन पास रखें।"
        if lang == "kannada":
            return f"ಆಂಬ್ಯುಲೆನ್ಸ್ ಮತ್ತು ಪೊಲೀಸ್ ಮಾಹಿತಿ ನೀಡಲಾಗಿದೆ. ಉಲ್ಲೇಖ: {ref}."
        return f"Ambulance and police are being notified. Reference: {ref}. Please stay on the line."
    if category == "medical":
        if lang == "hindi":
            return f"एम्बुलेंस भेजी जा रही है। संदर्भ: {ref}।"
        return f"Ambulance is being dispatched. Reference: {ref}."
    if category == "fire":
        if lang == "hindi":
            return f"फायर ब्रिगेड भेजी जा रही है। संदर्भ: {ref}।"
        return f"Fire brigade is being dispatched. Reference: {ref}."

    return (
        f"Your complaint has been registered. "
        f"Reference: {ref}. "
        "Please keep your phone reachable; an officer will follow up shortly."
    )


def _deterministic_response(
    call_state: CallState,
    analysis: CallAnalysis,
    resolution: str | None = None,
) -> str:
    """Fast local/demo response when no live LLM key is configured."""

    language = (analysis.language or call_state.language or "hindi").lower()
    phase = call_state.current_phase
    action_text = resolution or call_state.resolution or call_state.adapted_resolution
    ref = call_state.complaint_reference_id or f"SAH-{call_state.call_sid[-6:].upper()}"

    # ── Emergency fast-path ─────────────────────────────────────────
    is_emergency = analysis.urgency >= 0.85 and analysis.category in {
        "accident", "medical", "fire", "missing_person", "domestic"
    }
    if is_emergency and phase not in {"resolved", "handover", "handover_pending", "queued"}:
        emergency_responses = {
            "hindi": {
                "accident": "मैंने आपकी बात सुन ली - दुर्घटना हुई है। मैं अभी एम्बुलेंस और पुलिस भेज रही हूँ। कृपया अपना सटीक स्थान बताइए?",
                "medical": "मैंने सुना - मेडिकल इमरजेंसी है। मैं अभी एम्बुलेंस भेज रही हूँ। आप कहाँ हैं, पता बताइए?",
                "fire": "मैंने सुना - आग लगी है। मैं अभी फायर ब्रिगेड भेज रही हूँ। आपका पता क्या है?",
                "missing_person": "मैंने सुना - कोई गुम हो गया है। मैं अभी पुलिस को सूचित कर रही हूँ। कृपया नाम और आखिरी जगह बताइए?",
                "domestic": "आप सुरक्षित रहें। मैं अभी पुलिस भेज रही हूँ। आप किस पते पर हैं?",
            },
            "kannada": {
                "accident": "ನಿಮ್ಮ ಮಾತು ಕೇಳಿದೆ - ಅಪಘಾತವಾಗಿದೆ. ನಾನು ಈಗ ಆಂಬ್ಯುಲೆನ್ಸ್ ಮತ್ತು ಪೊಲೀಸ್ ಕಳುಹಿಸುತ್ತಿದ್ದೇನೆ. ನಿಮ್ಮ ನಿಖರ ಸ್ಥಳ ಹೇಳಿ?",
                "medical": "ಕೇಳಿದೆ - ವೈದ್ಯಕೀಯ ತುರ್ತು ಇದೆ. ಆಂಬ್ಯುಲೆನ್ಸ್ ಕಳುಹಿಸುತ್ತಿದ್ದೇನೆ. ನೀವು ಎಲ್ಲಿ ಇದ್ದೀರಿ?",
                "fire": "ಕೇಳಿದೆ - ಬೆಂಕಿ ಹತ್ತಿದೆ. ಫೈರ್ ಬ್ರಿಗೇಡ್ ಕಳುಹಿಸುತ್ತಿದ್ದೇನೆ. ನಿಮ್ಮ ವಿಳಾಸ ಏನು?",
                "missing_person": "ಕೇಳಿದೆ - ಯಾರೋ ಕಾಣೆಯಾಗಿದ್ದಾರೆ. ಪೊಲೀಸ್‌ಗೆ ತಿಳಿಸುತ್ತಿದ್ದೇನೆ. ಹೆಸರು ಮತ್ತು ಕೊನೆಯ ಸ್ಥಳ ಹೇಳಿ?",
                "domestic": "ಸುರಕ್ಷಿತರಾಗಿರಿ. ಪೊಲೀಸ್ ಕಳುಹಿಸುತ್ತಿದ್ದೇನೆ. ನಿಮ್ಮ ವಿಳಾಸ ಹೇಳಿ?",
            },
            "english": {
                "accident": "I heard you - there has been an accident. I am dispatching an ambulance and police right now. Please tell me your exact location?",
                "medical": "I heard you - this is a medical emergency. I am dispatching an ambulance right now. Where are you?",
                "fire": "I heard you - there is a fire. I am sending the fire brigade right now. What is your address?",
                "missing_person": "I heard you - someone is missing. I am alerting police right now. Please tell me their name and last known location?",
                "domestic": "Please stay safe. I am sending police to you right now. What is your address?",
            },
        }
        lang_responses = emergency_responses.get(language, emergency_responses["hindi"])
        cat_response = lang_responses.get(analysis.category)
        if cat_response:
            return cat_response
    # ────────────────────────────────────────────────────────────────

    english = {
        "queued": (
            "All officers are busy, but I have placed you in a priority queue. "
            "Say 'police', 'ambulance', or 'fire' for direct dispatch."
        ),
        "handover": "I am connecting you to a human officer right now. Your details have been passed on.",
        "handover_pending": "I am connecting you to a human officer right now. Your details have been passed on.",
        "resolved": (
            f"Done. {action_text or 'Your complaint has been registered.'} "
            f"Reference: {ref}. Help is on the way."
        ),
        "clarifying": "I heard you. Could you please tell me your exact location so I can dispatch help?",
        "vachan_partial": "Thank you. Please tell me the missing detail and I will confirm again.",
        "vachan_pending": call_state.vachan_prompt
        or f"I understood: {call_state.ai_summary or analysis.summary}. Is this correct?",
        "default": (
            f"I understood: {call_state.ai_summary or analysis.summary or 'your concern'}. "
            f"{action_text or 'I am taking action.'} Is this correct?"
        ),
    }
    hindi = {
        "queued": "सभी अधिकारी व्यस्त हैं, लेकिन आपकी कॉल प्राथमिकता में है। 'पुलिस', 'एम्बुलेंस', या 'फायर' कहें।",
        "handover": "मैं आपको अभी मानव अधिकारी से जोड़ रही हूँ। आपकी जानकारी पहुँचा दी गई है।",
        "handover_pending": "मैं आपको अभी मानव अधिकारी से जोड़ रही हूँ। आपकी जानकारी पहुँचा दी गई है।",
        "resolved": f"हो गया। संदर्भ संख्या: {ref}। मदद रास्ते में है।",
        "clarifying": "मैंने सुना। कृपया अपना सटीक पता बताइए ताकि मैं मदद भेज सकूँ?",
        "vachan_partial": "धन्यवाद। अधूरी जानकारी बताइए ताकि मैं फिर पुष्टि कर सकूँ।",
        "vachan_pending": call_state.vachan_prompt
        or f"मैंने यह समझा: {call_state.ai_summary or analysis.summary}। क्या यह सही है?",
        "default": f"मैंने समझा: {call_state.ai_summary or analysis.summary or 'आपकी समस्या'}। क्या यह सही है?",
    }
    kannada = {
        "queued": "ಎಲ್ಲಾ ಅಧಿಕಾರಿಗಳು ಬ್ಯುಸಿ. ನಿಮ್ಮ ಕರೆ ಆದ್ಯತೆಯಲ್ಲಿದೆ. 'ಪೊಲೀಸ್', 'ಆಂಬ್ಯುಲೆನ್ಸ್', ಅಥವಾ 'ಫೈರ್' ಹೇಳಿ.",
        "handover": "ನಿಮ್ಮ ವಿವರಗಳೊಂದಿಗೆ ಮಾನವ ಅಧಿಕಾರಿಗೆ ಈಗ ಸಂಪರ್ಕಿಸುತ್ತಿದ್ದೇನೆ.",
        "handover_pending": "ನಿಮ್ಮ ವಿವರಗಳೊಂದಿಗೆ ಮಾನವ ಅಧಿಕಾರಿಗೆ ಈಗ ಸಂಪರ್ಕಿಸುತ್ತಿದ್ದೇನೆ.",
        "resolved": f"ಮುಗಿದಿದೆ. ಉಲ್ಲೇಖ ಸಂಖ್ಯೆ: {ref}. ಸಹಾಯ ಬರುತ್ತಿದೆ.",
        "clarifying": "ಕೇಳಿದೆ. ದಯವಿಟ್ಟು ನಿಮ್ಮ ನಿಖರ ಸ್ಥಳ ಹೇಳಿ ಆಗ ಸಹಾಯ ಕಳುಹಿಸುತ್ತೇನೆ?",
        "vachan_partial": "ಧನ್ಯವಾದ. ತಪ್ಪಿದ ವಿವರ ಹೇಳಿ ಆಗ ದೃಢೀಕರಿಸುತ್ತೇನೆ.",
        "vachan_pending": call_state.vachan_prompt
        or f"ನಾನು ಹೀಗೆ ಅರ್ಥ ಮಾಡಿದ್ದೇನೆ: {call_state.ai_summary or analysis.summary}. ಸರಿಯೇ?",
        "default": f"ನಾನು ಅರ್ಥ ಮಾಡಿಕೊಂಡಿದ್ದು: {call_state.ai_summary or analysis.summary or 'ನಿಮ್ಮ ಸಮಸ್ಯೆ'}. ಸರಿಯೇ?",
    }
    templates = {"hindi": hindi, "kannada": kannada}.get(language, english)
    return templates.get(phase, templates["default"])


def _persist_call(call_state: CallState, analysis: CallAnalysis):
    """Persist call state through the repository layer."""
    try:
        call_repository.update_call_state(call_state, analysis=analysis)
    except Exception as e:
        print(f"⚠️  state persist error: {e}")

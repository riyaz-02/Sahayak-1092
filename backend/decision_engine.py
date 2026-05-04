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

import os
import json
import asyncio
from typing import Optional
from dataclasses import dataclass, field, asdict
from enum import Enum

from openai import AsyncOpenAI
from dotenv import load_dotenv

from backend import supabase_client as db

load_dotenv()

# ── LLM Client ──────────────────────────────────
client = AsyncOpenAI(
    api_key=os.getenv("OPENAI_API_KEY", ""),
    base_url=os.getenv("OPENAI_BASE_URL", None),  # Gemini: https://generativelanguage.googleapis.com/v1beta/openai/
)
MODEL = os.getenv("LLM_MODEL", "gpt-4o")


def extract_json(text: str) -> dict:
    """Extract JSON from LLM response — handles markdown code fences from Gemini."""
    import re
    text = re.sub(r"```(?:json)?\s*", "", text).strip().rstrip("`").strip()
    return json.loads(text)

# ── Data Models ──────────────────────────────────

class CallOutcome(str, Enum):
    AI_RESOLVED = "ai_resolved"
    HANDED_OVER = "handed_over"
    QUEUED = "queued"
    IN_PROGRESS = "in_progress"


class HandoverReason(str, Enum):
    LOW_CONFIDENCE = "low_confidence_after_retries"
    CALLER_REQUESTED = "caller_requested_human"
    HIGH_URGENCY = "extreme_urgency_distress"


@dataclass
class CallAnalysis:
    """Result of analysing a caller's utterance."""
    language: str = "english"          # detected language
    dialect: str = ""                  # regional dialect if any
    sentiment: str = "calm"            # calm, anxious, distressed, angry
    urgency: float = 0.5              # 0.0 (routine) → 1.0 (life-threatening)
    confidence: float = 0.7           # how confident the AI is in understanding
    category: str = "general"          # theft, accident, domestic, etc.
    summary: str = ""                  # one-line summary of the issue
    caller_wants_human: bool = False   # explicit request for human
    is_confirmation: Optional[bool] = None  # True/False/None for vachan loop
    raw_text: str = ""


@dataclass
class CallState:
    """Tracks the full state of an active call."""
    call_sid: str = ""
    caller_number: str = ""
    language: str = "english"
    dialect: str = ""
    transcript: list = field(default_factory=list)
    analyses: list = field(default_factory=list)
    current_phase: str = "greeting"   # greeting, listening, confirming, resolved, handover, queued
    attempt_count: int = 0            # for low-confidence retries
    ai_summary: str = ""
    resolution: str = ""
    similar_case: Optional[dict] = None
    agent_id: Optional[str] = None
    outcome: Optional[CallOutcome] = None
    handover_reason: Optional[HandoverReason] = None
    complaint_registered: bool = False
    queue_start_time: Optional[float] = None


# ── In-memory active calls ──────────────────────
active_calls: dict[str, CallState] = {}


def get_or_create_call(call_sid: str, caller_number: str = "") -> CallState:
    """Get existing call state or create new one."""
    if call_sid not in active_calls:
        active_calls[call_sid] = CallState(
            call_sid=call_sid,
            caller_number=caller_number,
        )
    return active_calls[call_sid]


def remove_call(call_sid: str):
    """Clean up after call ends."""
    active_calls.pop(call_sid, None)


# ──────────────────────────────────────────────
# 1. ANALYSE UTTERANCE
# ──────────────────────────────────────────────

ANALYSIS_SYSTEM_PROMPT = """You are the AI brain of Sahayak 1092, India's emergency helpline.
Analyse the caller's message and return a JSON object with these fields:
{
  "language": "kannada" | "hindi" | "english" | "telugu" | "tamil" | "urdu",
  "dialect": "string – regional dialect if identifiable, else empty",
  "sentiment": "calm" | "anxious" | "distressed" | "angry",
  "urgency": 0.0 to 1.0 (0 = routine, 0.5 = moderate, 0.8+ = life-threatening),
  "confidence": 0.0 to 1.0 (how well you understood the issue),
  "category": "theft" | "accident" | "domestic" | "cyber" | "noise" | "missing_person" | "suspicious_activity" | "medical" | "fire" | "traffic" | "general",
  "summary": "one-line summary of the caller's issue",
  "caller_wants_human": true/false,
  "is_confirmation": true | false | null (if this is a yes/no response to a confirmation question)
}
Only output valid JSON. No markdown, no explanation."""


async def analyse_utterance(text: str, call_state: CallState) -> CallAnalysis:
    """Use LLM to analyse a caller's utterance for language, sentiment, urgency, etc."""
    context = ""
    if call_state.transcript:
        recent = call_state.transcript[-6:]  # last 3 exchanges
        context = "\n".join([f"{t['role']}: {t['text']}" for t in recent])

    messages = [
        {"role": "system", "content": ANALYSIS_SYSTEM_PROMPT},
        {"role": "user", "content": f"Conversation so far:\n{context}\n\nNew caller message: \"{text}\""},
    ]

    for attempt in range(2):
        try:
            resp = await client.chat.completions.create(
                model=MODEL,
                messages=messages,
                temperature=0.1,
                max_tokens=300,
            )
            data = extract_json(resp.choices[0].message.content)
            analysis = CallAnalysis(
                language=data.get("language", "english"),
                dialect=data.get("dialect", ""),
                sentiment=data.get("sentiment", "calm"),
                urgency=float(data.get("urgency", 0.5)),
                confidence=float(data.get("confidence", 0.7)),
                category=data.get("category", "general"),
                summary=data.get("summary", text[:100]),
                caller_wants_human=data.get("caller_wants_human", False),
                is_confirmation=data.get("is_confirmation", None),
                raw_text=text,
            )
            call_state.language = analysis.language
            call_state.dialect = analysis.dialect
            call_state.analyses.append(asdict(analysis))
            return analysis
        except Exception as e:
            err_str = str(e)
            if "429" in err_str and attempt == 0:
                import re as _re
                wait = 5
                m = _re.search(r'retryDelay.*?(\d+)s', err_str)
                if m:
                    wait = min(int(m.group(1)), 15)
                print(f"⏳ LLM quota 429 — retrying in {wait}s...")
                await asyncio.sleep(wait)
                continue
            print(f"❌ Analysis error: {e}")
            return CallAnalysis(raw_text=text, summary=text[:100])
    return CallAnalysis(raw_text=text, summary=text[:100])


# ──────────────────────────────────────────────
# 2. SMART SIMILARITY DETECTION
# ──────────────────────────────────────────────

SIMILARITY_SYSTEM_PROMPT = """You are comparing a new helpline call with previously resolved cases.
Given the new issue summary and a list of resolved cases, determine:
1. Is any resolved case similar enough to apply the same resolution? (> 70% match)
2. If yes, which case and how should the resolution be adapted?

Return JSON:
{
  "is_similar": true/false,
  "matched_case_index": 0-based index or -1,
  "similarity_score": 0.0 to 1.0,
  "adapted_resolution": "resolution text adapted to the current situation"
}
Only valid JSON."""


async def find_similar_case(summary: str, category: str) -> Optional[dict]:
    """Check if a similar case exists in the knowledge base."""
    # Fetch resolved cases from DB
    cases = db.get_all_resolved_cases(limit=20)
    if not cases:
        return None

    cases_text = "\n".join([
        f"[{i}] Category: {c.get('category','?')} | Summary: {c.get('summary','')} | Resolution: {c.get('resolution','')}"
        for i, c in enumerate(cases)
    ])

    messages = [
        {"role": "system", "content": SIMILARITY_SYSTEM_PROMPT},
        {"role": "user", "content": f"New issue:\nCategory: {category}\nSummary: {summary}\n\nResolved cases:\n{cases_text}"},
    ]

    try:
        resp = await client.chat.completions.create(
            model=MODEL,
            messages=messages,
            temperature=0.1,
            max_tokens=400,
        )
        data = extract_json(resp.choices[0].message.content)
        if data.get("is_similar") and data.get("similarity_score", 0) >= 0.7:
            idx = data.get("matched_case_index", -1)
            if 0 <= idx < len(cases):
                return {
                    "matched_case": cases[idx],
                    "similarity_score": data["similarity_score"],
                    "adapted_resolution": data.get("adapted_resolution", cases[idx].get("resolution", "")),
                }
    except Exception as e:
        print(f"⚠️  Similarity search error: {e}")

    return None


# ──────────────────────────────────────────────
# 3. GENERATE AI RESPONSE
# ──────────────────────────────────────────────

RESPONSE_SYSTEM_PROMPT = """You are Sahayak, the AI voice assistant for India's 1092 emergency helpline.

RULES:
- Speak in the caller's detected language ({language}).
- Be calm, empathetic, and professional.
- Keep responses SHORT (2-4 sentences max) — this is a voice call.
- If you have a resolution, provide it clearly and ask for confirmation.
- For the Vachan (confirmation) loop: restate your understanding and ask "Is this correct? Please say yes or no."
- Never be rude. Always acknowledge the caller's distress.
- Use simple, everyday language. Avoid jargon.

CONTEXT:
Phase: {phase}
Issue summary: {summary}
Category: {category}
Sentiment: {sentiment}
Urgency: {urgency}"""


async def generate_response(call_state: CallState, analysis: CallAnalysis,
                            resolution: str = None) -> str:
    """Generate an empathetic, actionable response in the caller's language."""

    phase_instructions = {
        "greeting": "Greet the caller warmly and ask how you can help. Use their language.",
        "listening": "Acknowledge what they said, show empathy, and ask clarifying questions if needed.",
        "confirming": f"Restate your understanding and the proposed resolution. Ask for yes/no confirmation.\nProposed resolution: {resolution or 'pending'}",
        "resolved": f"Confirm the action taken, provide a reference/complaint number, and wish them well.\nResolution: {resolution or call_state.resolution}",
        "handover": "Inform the caller you are connecting them to a human officer. Reassure them.",
        "queued": "Inform the caller that all officers are busy. They are in a priority queue. Offer: Press 1 for Police, 2 for Ambulance, 3 for Fire services.",
    }

    instruction = phase_instructions.get(call_state.current_phase, "Respond helpfully.")

    messages = [
        {"role": "system", "content": RESPONSE_SYSTEM_PROMPT.format(
            language=analysis.language or call_state.language,
            phase=call_state.current_phase,
            summary=analysis.summary or call_state.ai_summary,
            category=analysis.category,
            sentiment=analysis.sentiment,
            urgency=analysis.urgency,
        )},
    ]

    # Add conversation history
    for t in call_state.transcript[-8:]:
        role = "user" if t["role"] == "caller" else "assistant"
        messages.append({"role": role, "content": t["text"]})

    messages.append({"role": "user", "content": f"[INSTRUCTION: {instruction}]\nCaller said: \"{analysis.raw_text}\""})

    try:
        resp = await client.chat.completions.create(
            model=MODEL,
            messages=messages,
            temperature=0.6,
            max_tokens=200,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        print(f"❌ Response generation error: {e}")
        # Fallback responses by language
        fallbacks = {
            "kannada": "ದಯವಿಟ್ಟು ಸ್ವಲ್ಪ ಕಾಯಿರಿ, ನಾನು ನಿಮಗೆ ಸಹಾಯ ಮಾಡುತ್ತೇನೆ.",
            "hindi": "कृपया थोड़ा इंतज़ार करें, मैं आपकी मदद कर रहा हूँ.",
            "english": "Please hold on, I am processing your request.",
        }
        return fallbacks.get(call_state.language, fallbacks["english"])


# ──────────────────────────────────────────────
# 4. AGENT ROUTING (Urgency-First + Language-Matched)
# ──────────────────────────────────────────────

def score_agent(agent: dict, call_state: CallState, analysis: CallAnalysis) -> float:
    """
    Score an agent for routing:
      50% urgency match (specialists)
      40% language/dialect fit
      10% shortest wait time
    """
    score = 0.0

    # Language match (40%)
    agent_langs = [l.lower() for l in agent.get("languages", [])]
    if call_state.language.lower() in agent_langs:
        score += 0.40
    elif any(l in agent_langs for l in ["english", "hindi"]):
        score += 0.15  # partial match

    # Specialty match (50%)
    agent_specs = [s.lower() for s in agent.get("specialties", [])]
    category = (analysis.category or "general").lower()
    if category in agent_specs:
        score += 0.50
    elif any(s in agent_specs for s in ["general"]):
        score += 0.20

    # Wait time (10%) – lower is better
    avg_wait = agent.get("avg_wait_sec", 60)
    wait_score = max(0, 1 - (avg_wait / 120))  # 0-120 sec range
    score += 0.10 * wait_score

    # Penalise high load
    load = agent.get("current_load", 0)
    if load > 2:
        score -= 0.15

    return round(score, 3)


async def route_to_agent(call_state: CallState, analysis: CallAnalysis) -> Optional[dict]:
    """Find the best available agent based on scoring algorithm."""
    agents = db.get_available_agents(language=call_state.language)
    if not agents:
        agents = db.get_available_agents()  # fallback: any language

    if not agents:
        return None

    scored = [(agent, score_agent(agent, call_state, analysis)) for agent in agents]
    scored.sort(key=lambda x: x[1], reverse=True)

    best_agent, best_score = scored[0]
    return {
        "agent": best_agent,
        "score": best_score,
        "reason": f"Language: {call_state.language}, Category: {analysis.category}",
    }


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

    # ── Step 1: Analyse ──
    analysis = await analyse_utterance(text, call_state)
    call_state.ai_summary = analysis.summary

    # ── Step 2: Check handover conditions ──
    needs_handover = False
    handover_reason = None

    # Condition 1: Caller explicitly asks for human
    if analysis.caller_wants_human:
        needs_handover = True
        handover_reason = HandoverReason.CALLER_REQUESTED

    # Condition 2: Extremely high urgency/distress
    elif analysis.urgency >= 0.9 and analysis.sentiment in ("distressed", "angry"):
        needs_handover = True
        handover_reason = HandoverReason.HIGH_URGENCY

    # Condition 3: Low confidence after 2 attempts
    elif analysis.confidence < 0.5:
        call_state.attempt_count += 1
        if call_state.attempt_count >= 2:
            needs_handover = True
            handover_reason = HandoverReason.LOW_CONFIDENCE

    if needs_handover:
        call_state.handover_reason = handover_reason
        route_result = await route_to_agent(call_state, analysis)

        if route_result:
            # Successful match → warm handover
            call_state.current_phase = "handover"
            call_state.outcome = CallOutcome.HANDED_OVER
            call_state.agent_id = route_result["agent"]["id"]
            response = await generate_response(call_state, analysis)
            call_state.transcript.append({"role": "sahayak", "text": response})

            # Persist to DB
            _persist_call(call_state, analysis)

            return {
                "response_text": response,
                "action": "handover",
                "agent": route_result["agent"],
                "call_state": asdict(call_state),
                "handover_context": {
                    "transcript": call_state.transcript,
                    "ai_summary": call_state.ai_summary,
                    "sentiment": analysis.sentiment,
                    "urgency": analysis.urgency,
                    "language": analysis.language,
                    "category": analysis.category,
                },
            }
        else:
            # No agent available → queue with IVR
            call_state.current_phase = "queued"
            call_state.outcome = CallOutcome.QUEUED
            import time
            call_state.queue_start_time = time.time()
            response = await generate_response(call_state, analysis)
            call_state.transcript.append({"role": "sahayak", "text": response})

            _persist_call(call_state, analysis)

            return {
                "response_text": response,
                "action": "queue",
                "call_state": asdict(call_state),
            }

    # ── Step 3: Confirmation Loop (Vachan) ──
    if call_state.current_phase == "confirming":
        if analysis.is_confirmation is True:
            # Confirmed! → Resolve
            call_state.current_phase = "resolved"
            call_state.outcome = CallOutcome.AI_RESOLVED

            # Register complaint
            try:
                call_log = db.get_call_log(call_sid)
                if call_log:
                    db.register_complaint(
                        call_log_id=call_log["id"],
                        category=analysis.category or "general",
                        description=call_state.ai_summary,
                    )
                    call_state.complaint_registered = True
            except Exception:
                pass

            # Add to knowledge base
            try:
                db.insert_resolved_case(
                    summary=call_state.ai_summary,
                    category=analysis.category or "general",
                    language=call_state.language,
                    resolution=call_state.resolution,
                )
            except Exception:
                pass

            response = await generate_response(call_state, analysis, call_state.resolution)
            call_state.transcript.append({"role": "sahayak", "text": response})
            _persist_call(call_state, analysis)

            return {
                "response_text": response,
                "action": "resolve",
                "call_state": asdict(call_state),
            }

        elif analysis.is_confirmation is False:
            # Not confirmed → go back to listening
            call_state.current_phase = "listening"
            call_state.attempt_count += 1
            response = await generate_response(call_state, analysis)
            call_state.transcript.append({"role": "sahayak", "text": response})
            return {
                "response_text": response,
                "action": "continue",
                "call_state": asdict(call_state),
            }

    # ── Step 4: Smart Similarity Detection ──
    if analysis.confidence >= 0.6 and call_state.current_phase in ("greeting", "listening"):
        similar = await find_similar_case(analysis.summary, analysis.category)
        if similar and similar.get("similarity_score", 0) >= 0.7:
            call_state.similar_case = similar["matched_case"]
            call_state.resolution = similar["adapted_resolution"]
            call_state.current_phase = "confirming"
            call_state.ai_summary = analysis.summary

            response = await generate_response(call_state, analysis, similar["adapted_resolution"])
            call_state.transcript.append({"role": "sahayak", "text": response})
            _persist_call(call_state, analysis)

            return {
                "response_text": response,
                "action": "continue",
                "call_state": asdict(call_state),
            }

    # ── Step 5: High confidence → AI takes ownership ──
    if analysis.confidence >= 0.7 and call_state.current_phase == "listening":
        # Generate resolution
        resolution = await _generate_resolution(analysis, call_state)
        call_state.resolution = resolution
        call_state.current_phase = "confirming"
        call_state.ai_summary = analysis.summary

        response = await generate_response(call_state, analysis, resolution)
        call_state.transcript.append({"role": "sahayak", "text": response})
        _persist_call(call_state, analysis)

        return {
            "response_text": response,
            "action": "continue",
            "call_state": asdict(call_state),
        }

    # ── Step 6: Continue listening ──
    if call_state.current_phase == "greeting":
        call_state.current_phase = "listening"

    response = await generate_response(call_state, analysis)
    call_state.transcript.append({"role": "sahayak", "text": response})

    return {
        "response_text": response,
        "action": "continue",
        "call_state": asdict(call_state),
    }


# ──────────────────────────────────────────────
# 6. GENERATE GREETING
# ──────────────────────────────────────────────

GREETING_TEMPLATES = {
    "kannada": "ನಮಸ್ಕಾರ, ಸಹಾಯಕ್ 1092 ಗೆ ಸ್ವಾಗತ. ನಾನು ನಿಮ್ಮ AI ಸಹಾಯಕ. ನಿಮ್ಮ ಸಮಸ್ಯೆಯನ್ನು ಹೇಳಿ, ನಾನು ತಕ್ಷಣ ಸಹಾಯ ಮಾಡುತ್ತೇನೆ.",
    "hindi": "नमस्ते, सहायक 1092 में आपका स्वागत है. मैं आपका AI सहायक हूँ. अपनी समस्या बताइए, मैं तुरंत मदद करूँगा.",
    "english": "Hello, welcome to Sahayak 1092. I am your AI assistant. Please describe your issue and I will help you immediately.",
}


def get_greeting(language: str = "english") -> str:
    """Get the initial greeting in the caller's language."""
    return GREETING_TEMPLATES.get(language.lower(), GREETING_TEMPLATES["english"])


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


async def _generate_resolution(analysis: CallAnalysis, call_state: CallState) -> str:
    """Generate a resolution for the caller's issue."""
    messages = [
        {"role": "system", "content": RESOLUTION_SYSTEM_PROMPT.format(language=analysis.language)},
        {"role": "user", "content": f"Category: {analysis.category}\nIssue: {analysis.summary}\nUrgency: {analysis.urgency}\nSentiment: {analysis.sentiment}"},
    ]
    try:
        resp = await client.chat.completions.create(
            model=MODEL,
            messages=messages,
            temperature=0.4,
            max_tokens=250,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        return f"Your complaint has been registered. Reference: SAH-{call_state.call_sid[-6:].upper()}. An officer will follow up within 30 minutes."


def _persist_call(call_state: CallState, analysis: CallAnalysis):
    """Persist call state to Supabase (fire-and-forget)."""
    try:
        db.update_call_log(
            call_sid=call_state.call_sid,
            language=call_state.language,
            dialect=call_state.dialect,
            sentiment=analysis.sentiment,
            urgency=analysis.urgency,
            confidence=analysis.confidence,
            transcript=call_state.transcript,
            ai_summary=call_state.ai_summary,
            outcome=call_state.outcome.value if call_state.outcome else None,
            agent_id=call_state.agent_id,
        )
    except Exception as e:
        print(f"⚠️  DB persist error: {e}")

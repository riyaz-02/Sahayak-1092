"""Deterministic voice-call script for polished demo recordings.

The normal Sahayak flow still handles real calls. This module is a deliberate
demo safety rail: when enabled, voice turns use exact prewritten responses
matched from the caller transcript instead of waiting on an LLM response.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any

from backend.config import Settings, get_settings
from backend.intelligence.schemas import (
    CallAnalysis,
    CallOutcome,
    CallPhase,
    CallState,
    ConfirmationStatus,
    DecisionAction,
    DecisionResult,
)
from backend.persistence.complaints import extract_location, get_complaint_registry
from backend.persistence.repository import get_call_repository, state_to_dict


AUTO_LANGUAGE_VALUES = {"", "auto", "detect", "detected"}
SCRIPTED_LANGUAGE_ALIASES = {"karnataka": "kannada", "kan": "kannada", "kn": "kannada"}
SCRIPTED_LANGUAGES = {"english", "hindi", "kannada"}

SCRIPTED_DEMO_COMMON_PHRASES = {
    "hindi": {
        "नमस्ते, आप 1092 सहायक से जुड़े हैं। मैं सुन रही हूँ, बताइए आपको किस मदद की ज़रूरत है?",
        "ठीक है, मैं सुधार कर रही हूँ। कृपया एक वाक्य में सही जानकारी बताइए।",
        "ठीक है, मैं आपको अभी human officer से जोड़ रही हूँ। आपकी बात और लोकेशन का सार officer को भेज दिया गया है।",
        "मैं सुन रही हूँ। कृपया एक वाक्य में बताइए: चोरी, दुर्घटना, आग, या किसी अधिकारी से बात करनी है?",
    },
    "english": {
        "Hello, you have reached Sahayak 1092. I am listening. Tell me what help you need.",
        "Okay, I am correcting it. Please tell me the correct information in one sentence.",
        "Okay, I am connecting you to a human officer now. I have already passed your summary and location.",
        "I am listening. Please say it in one sentence: theft, accident, fire, or human officer.",
    },
    "kannada": {
        "ನಮಸ್ಕಾರ, ನೀವು ಸಹಾಯಕ 1092 ಗೆ ಸಂಪರ್ಕಿಸಿದ್ದೀರಿ. ನಾನು ಕೇಳುತ್ತಿದ್ದೇನೆ, ನಿಮಗೆ ಯಾವ ಸಹಾಯ ಬೇಕು ಹೇಳಿ.",
        "ಸರಿ, ನಾನು ಅದನ್ನು ಸರಿಪಡಿಸುತ್ತಿದ್ದೇನೆ. ದಯವಿಟ್ಟು ಸರಿಯಾದ ಮಾಹಿತಿಯನ್ನು ಒಂದು ವಾಕ್ಯದಲ್ಲಿ ಹೇಳಿ.",
        "ಸರಿ, ನಾನು ಈಗ ನಿಮ್ಮನ್ನು ಮಾನವ ಅಧಿಕಾರಿಗೆ ಸಂಪರ್ಕಿಸುತ್ತಿದ್ದೇನೆ. ನಿಮ್ಮ ಸಾರಾಂಶ ಮತ್ತು ಸ್ಥಳವನ್ನು ಅಧಿಕಾರಿಗೆ ಕಳುಹಿಸಲಾಗಿದೆ.",
        "ನಾನು ಕೇಳುತ್ತಿದ್ದೇನೆ. ದಯವಿಟ್ಟು ಒಂದು ವಾಕ್ಯದಲ್ಲಿ ಹೇಳಿ: ಕಳ್ಳತನ, ಅಪಘಾತ, ಬೆಂಕಿ, ಅಥವಾ ಅಧಿಕಾರಿಯ ಜೊತೆ ಮಾತನಾಡಬೇಕು?",
    },
}

KANNADA_TEXT_HINTS = {
    "nanna",
    "nan",
    "nanage",
    "hattira",
    "alli",
    "agide",
    "aytu",
    "kallatana",
    "kaledu",
    "beku",
    "policege",
    "howdu",
    "haudu",
    "sari",
    "illa",
    "apaghata",
    "benki",
    "ambulens",
}

HINDI_TEXT_HINTS = {
    "mera",
    "meri",
    "mujhe",
    "chori",
    "ho gaya",
    "hua",
    "paas",
    "haan",
    "nahi",
    "sahi",
    "galat",
    "madad",
    "aag",
    "durghatna",
}


YES_WORDS = {
    "yes",
    "yeah",
    "yep",
    "correct",
    "right",
    "ok",
    "okay",
    "haan",
    "han",
    "ha",
    "haudu",
    "howdu",
    "sari",
    "sahi",
    "theek",
    "thik",
    "हाँ",
    "हा",
    "हां",
    "सही",
    "ठीक",
    "ಹೌದು",
    "ಹೌದ",
    "ಸರಿ",
    "ಸರಿಯಾಗಿದೆ",
    "ಹೌದು ಸರಿ",
}

NO_WORDS = {
    "no",
    "nope",
    "wrong",
    "incorrect",
    "nahi",
    "nahin",
    "illa",
    "tappu",
    "galat",
    "नहीं",
    "नही",
    "गलत",
    "ಇಲ್ಲ",
    "ತಪ್ಪು",
    "ಸರಿಯಿಲ್ಲ",
}

INTENT_KEYWORDS = {
    "human": {
        "human",
        "officer",
        "operator",
        "police se baat",
        "connect",
        "transfer",
        "अधिकारी",
        "ऑफिसर",
        "पुलिस से बात",
        "जोड़",
        "ಅಧಿಕಾರಿ",
        "ಪೊಲೀಸ್ ಜೊತೆ",
        "ಮಾತನಾಡಬೇಕು",
        "ಕನೆಕ್ಟ್",
        "ಸಂಪರ್ಕ",
    },
    "fire": {
        "fire",
        "aag",
        "burning",
        "smoke",
        "ಆಗ",
        "benki",
        "ಬೆಂಕಿ",
        "ಹೊಗೆ",
        "ಸುಡ",
        "आग",
        "धुआं",
        "जल",
    },
    "medical": {
        "ambulance",
        "medical",
        "accident",
        "injured",
        "bleeding",
        "crash",
        "एंबुलेंस",
        "एम्बुलेंस",
        "दुर्घटना",
        "एक्सीडेंट",
        "घायल",
        "खून",
        "ambulens",
        "apaghata",
        "ಅಂಬುಲೆನ್ಸ್",
        "ಆಂಬ್ಯುಲೆನ್ಸ್",
        "ಅಪಘಾತ",
        "ಗಾಯ",
        "ರಕ್ತ",
    },
    "theft": {
        "theft",
        "stolen",
        "steal",
        "snatch",
        "mobile",
        "phone",
        "wallet",
        "purse",
        "bag",
        "chori",
        "chor",
        "चोरी",
        "मोबाइल",
        "फोन",
        "पर्स",
        "बैग",
        "छीन",
        "kalla",
        "kallatana",
        "mobile kaledu",
        "ಮೋಬೈಲ್",
        "ಫೋನ್",
        "ಕಳ್ಳತನ",
        "ಕದ್ದು",
        "ಕಳೆದು",
        "ಪರ್ಸ್",
        "ಬ್ಯಾಗ್",
    },
    "harassment": {
        "harassment",
        "stalking",
        "follow",
        "domestic",
        "violence",
        "threat",
        "पीछा",
        "छेड़",
        "धमकी",
        "मार",
        "पति",
        "kirikiri",
        "himsachara",
        "ಹಿಂಬಾಲ",
        "ಕಿರುಕುಳ",
        "ಹಿಂಸೆ",
        "ಬೆದರಿಕೆ",
    },
}

KNOWN_LOCATIONS = (
    ("majestic", "Majestic bus stand"),
    ("मैजेस्टिक", "Majestic bus stand"),
    ("ಮೆಜೆಸ್ಟಿಕ್", "Majestic bus stand"),
    ("ಕೆಂಪೇಗೌಡ", "Kempegowda bus station"),
    ("bengaluru", "Bengaluru"),
    ("bangalore", "Bengaluru"),
    ("ಬೆಂಗಳೂರು", "Bengaluru"),
    ("bus stand", "bus stand"),
    ("बस स्टैंड", "bus stand"),
    ("ಬಸ್ ಸ್ಟ್ಯಾಂಡ್", "bus stand"),
    ("ಬಸ್ ನಿಲ್ದಾಣ", "bus stand"),
    ("metro", "metro station"),
    ("मेट्रो", "metro station"),
    ("ಮೆಟ್ರೋ", "metro station"),
    ("railway", "railway station"),
    ("रेलवे", "railway station"),
    ("ರೈಲು", "railway station"),
    ("market", "market"),
    ("बाज़ार", "market"),
    ("बाजार", "market"),
    ("ಮಾರುಕಟ್ಟೆ", "market"),
    ("college", "college"),
    ("कॉलेज", "college"),
    ("ಕಾಲೇಜ್", "college"),
    ("school", "school"),
    ("स्कूल", "school"),
    ("ಶಾಲೆ", "school"),
)


@dataclass(frozen=True)
class ScriptedTurn:
    response_text: str
    action: DecisionAction
    analysis: CallAnalysis
    matched_intent: str
    reference_id: str = ""


def scripted_voice_demo_enabled(settings: Settings | None = None) -> bool:
    cfg = settings or get_settings()
    return bool(cfg.voice_scripted_demo_enabled)


def scripted_demo_language_mode(settings: Settings | None = None) -> str:
    cfg = settings or get_settings()
    configured = (cfg.voice_script_language or "").strip().lower()
    return SCRIPTED_LANGUAGE_ALIASES.get(configured, configured)


def scripted_demo_language_is_auto(settings: Settings | None = None) -> bool:
    return scripted_demo_language_mode(settings) in AUTO_LANGUAGE_VALUES


def scripted_demo_stt_language(call_state: CallState, settings: Settings | None = None) -> str:
    """Return the language hint to send to STT for scripted demo mode."""

    if scripted_demo_language_is_auto(settings):
        return "unknown"
    return scripted_demo_language(call_state.language, call_state, settings)


def scripted_demo_language(
    requested_language: str | None = "",
    call_state: CallState | None = None,
    settings: Settings | None = None,
) -> str:
    language_mode = scripted_demo_language_mode(settings)
    language = "" if language_mode in AUTO_LANGUAGE_VALUES else language_mode
    language = (language or requested_language or "").strip().lower()
    if not language and call_state:
        language = (call_state.language or "").strip().lower()
    language = SCRIPTED_LANGUAGE_ALIASES.get(language, language)
    return language if language in SCRIPTED_LANGUAGES else "hindi"


def infer_scripted_language_from_text(text: str, fallback: str = "hindi") -> str:
    """Best-effort script language inference when STT does not return one."""

    clean = _normalise(text)
    if re.search(r"[\u0C80-\u0CFF]", text or ""):
        return "kannada"
    if re.search(r"[\u0900-\u097F]", text or ""):
        return "hindi"
    if any(hint in clean for hint in KANNADA_TEXT_HINTS):
        return "kannada"
    if any(hint in clean for hint in HINDI_TEXT_HINTS):
        return "hindi"
    if any(word in clean for word in ("theft", "stolen", "accident", "fire", "officer", "help")):
        return "english"
    return scripted_demo_language(fallback)


def scripted_demo_greeting(language: str | None = "", settings: Settings | None = None) -> str:
    lang = scripted_demo_language(language, settings=settings)
    if lang == "english":
        return "Hello, you have reached Sahayak 1092. I am listening. Tell me what help you need."
    if lang == "kannada":
        return "ನಮಸ್ಕಾರ, ನೀವು ಸಹಾಯಕ 1092 ಗೆ ಸಂಪರ್ಕಿಸಿದ್ದೀರಿ. ನಾನು ಕೇಳುತ್ತಿದ್ದೇನೆ, ನಿಮಗೆ ಯಾವ ಸಹಾಯ ಬೇಕು ಹೇಳಿ."
    return "नमस्ते, आप 1092 सहायक से जुड़े हैं। मैं सुन रही हूँ, बताइए आपको किस मदद की ज़रूरत है?"


def _normalise(text: str) -> str:
    return " ".join((text or "").strip().lower().split())


def _contains_any(text: str, words: set[str]) -> bool:
    return any(word in text for word in words)


def _detect_intent(text: str, call_state: CallState) -> str:
    clean = _normalise(text)
    if call_state.current_phase == CallPhase.VACHAN_PENDING.value:
        if _contains_any(clean, YES_WORDS):
            return "confirm_yes"
        if _contains_any(clean, NO_WORDS):
            return "confirm_no"
    if call_state.current_phase == CallPhase.CLARIFYING.value and _detect_location(text):
        last_category = _last_category(call_state)
        if last_category == "theft":
            return "theft"
        if last_category in {"medical", "accident"}:
            return "medical"
        if last_category == "fire":
            return "fire"
        if last_category == "harassment":
            return "harassment"

    for intent in ("human", "fire", "medical", "theft", "harassment"):
        if _contains_any(clean, INTENT_KEYWORDS[intent]):
            return intent
    if _contains_any(clean, YES_WORDS):
        return "confirm_yes"
    if _contains_any(clean, NO_WORDS):
        return "confirm_no"
    return "fallback"


def _detect_location(text: str) -> str:
    clean = _normalise(text)
    for keyword, label in KNOWN_LOCATIONS:
        if keyword in clean:
            return label

    location = extract_location(text)
    if location:
        return location

    patterns = [
        r"(?:near|at|in|outside)\s+([A-Za-z0-9][A-Za-z0-9 .,'/-]{2,70})",
        r"(?:के पास|में|पर)\s*([A-Za-z0-9\u0900-\u097F][A-Za-z0-9\u0900-\u097F .,'/-]{2,70})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip(" .,")[:90]
    return ""


def _last_category(call_state: CallState) -> str:
    for analysis in reversed(call_state.analyses):
        category = str(analysis.get("category") or "").strip()
        if category:
            return category
    summary = _normalise(call_state.ai_summary)
    if any(word in summary for word in ("mobile", "phone", "चोरी", "मोबाइल", "ಮೋಬೈಲ್", "ಕಳ್ಳತನ")):
        return "theft"
    if any(word in summary for word in ("accident", "ambulance", "दुर्घटना", "एंबुलेंस", "ಅಪಘಾತ", "ಆಂಬ್ಯುಲೆನ್ಸ್")):
        return "medical"
    if any(word in summary for word in ("fire", "आग", "ಬೆಂಕಿ")):
        return "fire"
    return "general"


def _summary_for(intent: str, location: str, text: str, language: str) -> tuple[str, str]:
    where = f" near {location}" if location else ""
    if language == "english":
        if intent == "theft":
            return "theft", f"Mobile theft reported{where}."
        if intent == "medical":
            return "medical", f"Medical or accident emergency reported{where}."
        if intent == "fire":
            return "fire", f"Fire emergency reported{where}."
        if intent == "harassment":
            return "harassment", f"Caller reports harassment or threat{where}."
        return "general", text[:220]

    if language == "kannada":
        where_kn = f" {location} ಹತ್ತಿರ" if location else ""
        if intent == "theft":
            return "theft", f"ಮೊಬೈಲ್ ಕಳ್ಳತನದ ದೂರು{where_kn}."
        if intent == "medical":
            return "medical", f"ಅಪಘಾತ ಅಥವಾ ವೈದ್ಯಕೀಯ ತುರ್ತು ಪರಿಸ್ಥಿತಿ{where_kn}."
        if intent == "fire":
            return "fire", f"ಬೆಂಕಿ ತುರ್ತು ಮಾಹಿತಿ{where_kn}."
        if intent == "harassment":
            return "harassment", f"ಕಾಲರ್ ಕಿರುಕುಳ ಅಥವಾ ಬೆದರಿಕೆಯ ಬಗ್ಗೆ ತಿಳಿಸಿದ್ದಾರೆ{where_kn}."
        return "general", text[:220]

    where_hi = f" {location} के पास" if location else ""
    if intent == "theft":
        return "theft", f"मोबाइल चोरी की शिकायत{where_hi}."
    if intent == "medical":
        return "medical", f"दुर्घटना या मेडिकल आपात स्थिति{where_hi}."
    if intent == "fire":
        return "fire", f"आग की आपात सूचना{where_hi}."
    if intent == "harassment":
        return "harassment", f"कॉलर ने छेड़छाड़ या धमकी की सूचना दी{where_hi}."
    return "general", text[:220]


def _reference(call_state: CallState) -> str:
    if call_state.complaint_reference_id:
        return call_state.complaint_reference_id
    suffix = re.sub(r"[^A-Z0-9]", "", (call_state.call_sid or "DEMO").upper())[-6:] or "DEMO"
    return f"SAH-DEMO-{suffix}"


def _make_analysis(
    *,
    text: str,
    language: str,
    intent: str,
    category: str,
    summary: str,
) -> CallAnalysis:
    urgency = {
        "medical": 0.92,
        "fire": 0.94,
        "harassment": 0.84,
        "human": 0.72,
        "theft": 0.68,
        "confirm_yes": 0.55,
        "confirm_no": 0.45,
    }.get(intent, 0.5)
    return CallAnalysis(
        language=language,
        sentiment="distressed" if urgency >= 0.8 else "anxious",
        urgency=urgency,
        confidence=0.96,
        category=category,
        summary=summary,
        caller_wants_human=intent == "human",
        is_confirmation=intent in {"confirm_yes", "confirm_no"},
        confirmation_status=(
            ConfirmationStatus.YES.value
            if intent == "confirm_yes"
            else ConfirmationStatus.NO.value
            if intent == "confirm_no"
            else ConfirmationStatus.NONE.value
        ),
        raw_text=text,
    )


def _response_for(
    *,
    intent: str,
    language: str,
    location: str,
    reference_id: str,
) -> tuple[str, DecisionAction]:
    if language == "english":
        if intent == "confirm_yes":
            return (
                f"Your complaint is registered. Reference number {reference_id}. "
                "The nearest police team has been notified; please keep your phone on.",
                DecisionAction.RESOLVE,
            )
        if intent == "confirm_no":
            return (
                "Okay, I am correcting it. Please tell me the correct information in one sentence.",
                DecisionAction.CONTINUE,
            )
        if intent == "human":
            return (
                "Okay, I am connecting you to a human officer now. "
                "I have already passed your summary and location.",
                DecisionAction.HANDOVER,
            )
        if intent == "medical":
            if location:
                return (
                    f"Location noted: {location}. Ambulance and police are being alerted now; please stay on the line.",
                    DecisionAction.CONTINUE,
                )
            return (
                "I understand this is urgent. I am alerting ambulance and police now. "
                "Please tell me your exact location.",
                DecisionAction.CONTINUE,
            )
        if intent == "fire":
            return (
                "I understood the fire emergency. I am alerting fire services and police now. "
                "Please tell me the building or road name.",
                DecisionAction.CONTINUE,
            )
        if intent == "harassment":
            return (
                "Your safety is my priority. I am sending this to a trained officer; "
                "move to a safe place if you can, and tell me your location.",
                DecisionAction.HANDOVER,
            )
        if intent == "theft":
            if location:
                return (
                    f"I understood: your mobile was stolen near {location}. "
                    "I am registering the complaint now. Is this information correct?",
                    DecisionAction.CONTINUE,
                )
            return (
                "Okay, I will register your mobile theft complaint. "
                "Please clearly tell me where the incident happened.",
                DecisionAction.CONTINUE,
            )
        return (
            "I am listening. Please say it in one sentence: theft, accident, fire, or human officer.",
            DecisionAction.CONTINUE,
        )

    if language == "kannada":
        if intent == "confirm_yes":
            return (
                f"ನಿಮ್ಮ ದೂರು ದಾಖಲಾಗಿದೆ. ಉಲ್ಲೇಖ ಸಂಖ್ಯೆ {reference_id}. "
                "ಹತ್ತಿರದ ಪೊಲೀಸ್ ತಂಡಕ್ಕೆ ಮಾಹಿತಿ ಕಳುಹಿಸಲಾಗಿದೆ; ದಯವಿಟ್ಟು ನಿಮ್ಮ ಫೋನ್ ಆನ್ ಇಡಿ.",
                DecisionAction.RESOLVE,
            )
        if intent == "confirm_no":
            return (
                "ಸರಿ, ನಾನು ಅದನ್ನು ಸರಿಪಡಿಸುತ್ತಿದ್ದೇನೆ. ದಯವಿಟ್ಟು ಸರಿಯಾದ ಮಾಹಿತಿಯನ್ನು ಒಂದು ವಾಕ್ಯದಲ್ಲಿ ಹೇಳಿ.",
                DecisionAction.CONTINUE,
            )
        if intent == "human":
            return (
                "ಸರಿ, ನಾನು ಈಗ ನಿಮ್ಮನ್ನು ಮಾನವ ಅಧಿಕಾರಿಗೆ ಸಂಪರ್ಕಿಸುತ್ತಿದ್ದೇನೆ. "
                "ನಿಮ್ಮ ಸಾರಾಂಶ ಮತ್ತು ಸ್ಥಳವನ್ನು ಅಧಿಕಾರಿಗೆ ಕಳುಹಿಸಲಾಗಿದೆ.",
                DecisionAction.HANDOVER,
            )
        if intent == "medical":
            if location:
                return (
                    f"ಸ್ಥಳವನ್ನು ನೋಟ್ ಮಾಡಿದ್ದೇನೆ: {location}. "
                    "ಆಂಬ್ಯುಲೆನ್ಸ್ ಮತ್ತು ಪೊಲೀಸರಿಗೆ ತಕ್ಷಣ ಅಲರ್ಟ್ ಮಾಡಲಾಗುತ್ತಿದೆ; ದಯವಿಟ್ಟು ಲೈನಿನಲ್ಲಿ ಇರಿ.",
                    DecisionAction.CONTINUE,
                )
            return (
                "ನಾನು ತುರ್ತು ಪರಿಸ್ಥಿತಿಯನ್ನು ಅರ್ಥ ಮಾಡಿಕೊಂಡಿದ್ದೇನೆ. ಆಂಬ್ಯುಲೆನ್ಸ್ ಮತ್ತು ಪೊಲೀಸರಿಗೆ ಈಗ ಅಲರ್ಟ್ ಮಾಡುತ್ತಿದ್ದೇನೆ. "
                "ದಯವಿಟ್ಟು ನಿಮ್ಮ ನಿಖರವಾದ ಸ್ಥಳ ಹೇಳಿ.",
                DecisionAction.CONTINUE,
            )
        if intent == "fire":
            return (
                "ನಾನು ಬೆಂಕಿಯ ತುರ್ತು ಮಾಹಿತಿಯನ್ನು ಅರ್ಥ ಮಾಡಿಕೊಂಡಿದ್ದೇನೆ. ಫೈರ್ ಸರ್ವಿಸ್ ಮತ್ತು ಪೊಲೀಸರಿಗೆ ಈಗ ಅಲರ್ಟ್ ಮಾಡುತ್ತಿದ್ದೇನೆ. "
                "ದಯವಿಟ್ಟು ಕಟ್ಟಡ ಅಥವಾ ರಸ್ತೆಯ ಹೆಸರು ಹೇಳಿ.",
                DecisionAction.CONTINUE,
            )
        if intent == "harassment":
            return (
                "ನಿಮ್ಮ ಸುರಕ್ಷತೆ ನನಗೆ ಮುಖ್ಯ. ತರಬೇತಿ ಪಡೆದ ಅಧಿಕಾರಿಗೆ ಮಾಹಿತಿ ಕಳುಹಿಸುತ್ತಿದ್ದೇನೆ; "
                "ಸಾಧ್ಯವಾದರೆ ಸುರಕ್ಷಿತ ಸ್ಥಳಕ್ಕೆ ಹೋಗಿ, ಮತ್ತು ನಿಮ್ಮ ಸ್ಥಳ ಹೇಳಿ.",
                DecisionAction.HANDOVER,
            )
        if intent == "theft":
            if location:
                return (
                    f"ಸರಿ, ನಾನು ಅರ್ಥ ಮಾಡಿಕೊಂಡಿದ್ದು: ನಿಮ್ಮ ಮೊಬೈಲ್ {location} ಹತ್ತಿರ ಕಳ್ಳತನವಾಗಿದೆ. "
                    "ನಾನು ಈಗ ದೂರು ದಾಖಲಿಸುತ್ತಿದ್ದೇನೆ. ಈ ಮಾಹಿತಿ ಸರಿಯೇ?",
                    DecisionAction.CONTINUE,
                )
            return (
                "ಸರಿ, ನಾನು ನಿಮ್ಮ ಮೊಬೈಲ್ ಕಳ್ಳತನದ ದೂರು ದಾಖಲಿಸುತ್ತೇನೆ. "
                "ದಯವಿಟ್ಟು ಘಟನೆ ನಡೆದ ಸ್ಥಳವನ್ನು ಸ್ಪಷ್ಟವಾಗಿ ಹೇಳಿ.",
                DecisionAction.CONTINUE,
            )
        return (
            "ನಾನು ಕೇಳುತ್ತಿದ್ದೇನೆ. ದಯವಿಟ್ಟು ಒಂದು ವಾಕ್ಯದಲ್ಲಿ ಹೇಳಿ: ಕಳ್ಳತನ, ಅಪಘಾತ, ಬೆಂಕಿ, ಅಥವಾ ಅಧಿಕಾರಿಯ ಜೊತೆ ಮಾತನಾಡಬೇಕು?",
            DecisionAction.CONTINUE,
        )

    if intent == "confirm_yes":
        return (
            f"आपकी शिकायत दर्ज हो गई है। संदर्भ नंबर {reference_id} है। "
            "नज़दीकी पुलिस टीम को सूचना भेज दी गई है; कृपया अपना फोन चालू रखें।",
            DecisionAction.RESOLVE,
        )
    if intent == "confirm_no":
        return (
            "ठीक है, मैं सुधार कर रही हूँ। कृपया एक वाक्य में सही जानकारी बताइए।",
            DecisionAction.CONTINUE,
        )
    if intent == "human":
        return (
            "ठीक है, मैं आपको अभी human officer से जोड़ रही हूँ। "
            "आपकी बात और लोकेशन का सार officer को भेज दिया गया है।",
            DecisionAction.HANDOVER,
        )
    if intent == "medical":
        if location:
            return (
                f"लोकेशन नोट कर ली है: {location}. "
                "एम्बुलेंस और पुलिस को तुरंत अलर्ट किया जा रहा है; कृपया लाइन पर बने रहें।",
                DecisionAction.CONTINUE,
            )
        return (
            "मैंने आपात स्थिति समझ ली है। एम्बुलेंस और पुलिस को अभी अलर्ट कर रही हूँ। "
            "कृपया अपनी सटीक लोकेशन बताइए।",
            DecisionAction.CONTINUE,
        )
    if intent == "fire":
        return (
            "मैंने आग की सूचना समझ ली है। फायर ब्रिगेड और पुलिस को अभी अलर्ट कर रही हूँ। "
            "कृपया बिल्डिंग या सड़क का नाम बताइए।",
            DecisionAction.CONTINUE,
        )
    if intent == "harassment":
        return (
            "मैं आपकी सुरक्षा को प्राथमिकता दे रही हूँ। एक प्रशिक्षित अधिकारी को जानकारी भेज रही हूँ; "
            "अगर आप खतरे में हैं तो सुरक्षित जगह पर रहें और अपनी लोकेशन बताइए।",
            DecisionAction.HANDOVER,
        )
    if intent == "theft":
        if location:
            return (
                f"ठीक है, मैंने समझा: आपका मोबाइल {location} के पास चोरी हुआ है। "
                "मैं अभी शिकायत दर्ज कर रही हूँ। क्या यह जानकारी सही है?",
                DecisionAction.CONTINUE,
            )
        return (
            "ठीक है, मैं आपकी मोबाइल चोरी की शिकायत दर्ज करूँगी। "
            "कृपया साफ़-साफ़ बताइए, घटना किस जगह हुई?",
            DecisionAction.CONTINUE,
        )
    return (
        "मैं सुन रही हूँ। कृपया एक वाक्य में बताइए: चोरी, दुर्घटना, आग, या किसी अधिकारी से बात करनी है?",
        DecisionAction.CONTINUE,
    )


def _apply_state(
    *,
    call_state: CallState,
    turn: ScriptedTurn,
    text: str,
) -> None:
    call_state.language = turn.analysis.language
    call_state.dialect = turn.analysis.dialect
    call_state.analyses.append(turn.analysis.as_event_payload())
    call_state.ai_summary = turn.analysis.summary or call_state.ai_summary

    if turn.action == DecisionAction.RESOLVE:
        call_state.current_phase = CallPhase.RESOLVED.value
        call_state.outcome = CallOutcome.AI_RESOLVED
        call_state.complaint_registered = True
        call_state.complaint_reference_id = turn.reference_id
    elif turn.action == DecisionAction.HANDOVER:
        call_state.current_phase = CallPhase.HANDOVER_PENDING.value
        call_state.outcome = CallOutcome.HANDED_OVER
        call_state.handover_context = {
            "mode": "scripted_demo",
            "summary": call_state.ai_summary,
            "caller_text": text,
        }
    elif turn.matched_intent in {"theft"} and turn.action == DecisionAction.CONTINUE:
        call_state.current_phase = CallPhase.VACHAN_PENDING.value if _detect_location(text) else CallPhase.CLARIFYING.value
        call_state.vachan_prompt = turn.response_text
    elif turn.matched_intent == "confirm_no":
        call_state.current_phase = CallPhase.CLARIFYING.value
    else:
        call_state.current_phase = CallPhase.COLLECTING_ISSUE.value

    call_state.transcript.append({"role": "caller", "text": text})
    call_state.transcript.append({"role": "sahayak", "text": turn.response_text})


def process_scripted_voice_turn(
    *,
    call_state: CallState,
    text: str,
    language: str = "",
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Return an exact scripted voice response for the current caller utterance."""

    cfg = settings or get_settings()
    repo = get_call_repository()
    started_at = time.perf_counter()
    if scripted_demo_language_is_auto(cfg):
        lang = infer_scripted_language_from_text(text, fallback=language or call_state.language)
    else:
        lang = scripted_demo_language(language, call_state, cfg)
    intent = _detect_intent(text, call_state)
    location = _detect_location(text)
    category, summary = _summary_for(intent, location, text, lang)

    if intent == "confirm_yes":
        category = _last_category(call_state)
        summary = call_state.ai_summary or summary
    elif intent == "confirm_no":
        category = _last_category(call_state)
        summary = call_state.ai_summary or summary
    elif intent == "human":
        category = _last_category(call_state)
        summary = call_state.ai_summary or summary

    reference_id = _reference(call_state)
    response_text, action = _response_for(
        intent=intent,
        language=lang,
        location=location,
        reference_id=reference_id,
    )
    analysis = _make_analysis(
        text=text,
        language=lang,
        intent=intent,
        category=category,
        summary=summary,
    )
    turn = ScriptedTurn(
        response_text=response_text,
        action=action,
        analysis=analysis,
        matched_intent=intent,
        reference_id=reference_id,
    )

    repo.append_call_event(
        call_sid=call_state.call_sid,
        event_type="utterance_received",
        payload={"text": text, "mode": "scripted_demo"},
        call_state=call_state,
    )
    _apply_state(call_state=call_state, turn=turn, text=text)

    if action == DecisionAction.RESOLVE and not get_complaint_registry().get_by_call_sid(call_state.call_sid):
        record = get_complaint_registry().register_ai_resolved_complaint(
            call_state=call_state,
            analysis=analysis,
            category=category,
            resolution=response_text,
        )
        call_state.complaint_reference_id = record.get("reference_id") or reference_id
        turn = ScriptedTurn(
            response_text=response_text.replace(reference_id, call_state.complaint_reference_id),
            action=action,
            analysis=analysis,
            matched_intent=intent,
            reference_id=call_state.complaint_reference_id,
        )
        call_state.transcript[-1]["text"] = turn.response_text

    repo.update_call_state(call_state, analysis=analysis)
    repo.append_call_event(
        call_sid=call_state.call_sid,
        event_type="analysis_completed",
        payload={**analysis.as_event_payload(), "latency_ms": 0.0, "mode": "scripted_demo"},
        call_state=call_state,
        analysis=analysis,
    )
    repo.append_call_event(
        call_sid=call_state.call_sid,
        event_type="scripted_demo_matched",
        payload={
            "intent": intent,
            "response_text": turn.response_text,
            "location": location,
            "latency_ms": round((time.perf_counter() - started_at) * 1000, 2),
        },
        call_state=call_state,
        analysis=analysis,
    )
    if call_state.current_phase == CallPhase.VACHAN_PENDING.value:
        repo.append_call_event(
            call_sid=call_state.call_sid,
            event_type="vachan_requested",
            payload={"prompt": turn.response_text, "mode": "scripted_demo"},
            call_state=call_state,
            analysis=analysis,
        )
    if action == DecisionAction.RESOLVE:
        repo.append_call_event(
            call_sid=call_state.call_sid,
            event_type="vachan_confirmed",
            payload={"reference_id": call_state.complaint_reference_id, "mode": "scripted_demo"},
            call_state=call_state,
            analysis=analysis,
        )
        repo.append_call_event(
            call_sid=call_state.call_sid,
            event_type="complaint_registered",
            payload={"reference_id": call_state.complaint_reference_id, "mode": "scripted_demo"},
            call_state=call_state,
            analysis=analysis,
        )

    return DecisionResult(
        response_text=turn.response_text,
        action=action,
        call_state=state_to_dict(call_state),
        analysis=analysis,
        reason=f"scripted_demo:{intent}",
    ).as_response()


def preview_scripted_voice_turn(
    *,
    text: str,
    language: str = "",
    phase: str = CallPhase.COLLECTING_ISSUE.value,
    previous_category: str = "",
    previous_summary: str = "",
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Preview the scripted response without writing call state or complaints."""

    cfg = settings or get_settings()
    state = CallState(
        call_sid="script-preview",
        language=scripted_demo_language(language, settings=cfg),
        current_phase=phase or CallPhase.COLLECTING_ISSUE.value,
        ai_summary=previous_summary or "",
    )
    if previous_category:
        state.analyses.append({"category": previous_category})

    if scripted_demo_language_is_auto(cfg):
        lang = infer_scripted_language_from_text(text, fallback=language or state.language)
    else:
        lang = scripted_demo_language(language, state, cfg)
    intent = _detect_intent(text, state)
    location = _detect_location(text)
    category, summary = _summary_for(intent, location, text, lang)

    if intent in {"confirm_yes", "confirm_no", "human"}:
        category = _last_category(state)
        summary = state.ai_summary or summary

    reference_id = _reference(state)
    response_text, action = _response_for(
        intent=intent,
        language=lang,
        location=location,
        reference_id=reference_id,
    )
    analysis = _make_analysis(
        text=text,
        language=lang,
        intent=intent,
        category=category,
        summary=summary,
    )
    return {
        "scripted_demo_enabled": cfg.voice_scripted_demo_enabled,
        "language_mode": cfg.voice_script_language or "auto",
        "stt_language_hint": "unknown" if scripted_demo_language_is_auto(cfg) else lang,
        "detected_script_language": lang,
        "matched_intent": intent,
        "location": location,
        "response_text": response_text,
        "action": action.value,
        "analysis": analysis.as_event_payload(),
    }

"""Schema-first call analyzers.

The production path can use an LLM with structured JSON output, while local
development and tests always have a deterministic analyzer that understands the
core demo scenarios without any network or paid provider.
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any

from backend.config import Settings, get_settings
from backend.intelligence.schemas import (
    CallAnalysis,
    CallPhase,
    CallState,
    ConfirmationStatus,
)


ANALYSIS_SYSTEM_PROMPT = """You are the AI brain of Sahayak 1092, India's emergency helpline.
Analyse the caller's message and return one JSON object matching the provided schema.

Rules:
- Detect language, dialect, sentiment, urgency, confidence, category, and summary.
- `caller_wants_human` is true only when the caller asks for an officer/person/human.
- During Vachan phases, set `confirmation_status` to yes, no, partial, or none.
- For partial confirmation, include `correction_text` and `missing_fields`.
- `is_confirmation` is true for yes, false for no, and null for partial/none.
- Prefer safe handover signals over autonomous confidence when the caller is distressed.
- Output only JSON; no markdown or explanation."""


def extract_json(text: str) -> dict[str, Any]:
    """Extract JSON from an LLM response, including fenced responses."""

    cleaned = re.sub(r"```(?:json)?\s*", "", text or "").strip().rstrip("`").strip()
    return json.loads(cleaned)


def _contains_any(text: str, keywords: set[str]) -> bool:
    return any(keyword in text for keyword in keywords)


def _word_count(text: str) -> int:
    return len([part for part in re.split(r"\s+", text.strip()) if part])


class DeterministicAnalyzer:
    """Offline analyzer for tests, demos, and provider outages."""

    ENGLISH_HUMAN_REQUEST = {
        "human",
        "officer",
        "agent",
        "person",
        "police officer",
        "connect me",
        "talk to police",
        "speak to police",
        "real person",
    }
    HINDI_HUMAN_REQUEST = {
        "अधिकारी",
        "इंसान",
        "पुलिस से बात",
        "आदमी से बात",
        "मानव",
    }
    KANNADA_HUMAN_REQUEST = {
        "ಅಧಿಕಾರಿ",
        "ಮಾನವ",
        "ಪೊಲೀಸ್ ಜೊತೆ",
        "ಪೊಲೀಸರ ಜೊತೆ",
        "ವ್ಯಕ್ತಿಯೊಂದಿಗೆ",
    }

    YES_WORDS = {
        "yes",
        "yeah",
        "yep",
        "correct",
        "right",
        "ok",
        "okay",
        "haudu",
        "ಹೌದು",
        "ಸರಿ",
        "ಹೌ",
        "haan",
        "hanji",
        "हाँ",
        "हां",
        "सही",
    }
    NO_WORDS = {
        "no",
        "nope",
        "wrong",
        "incorrect",
        "illa",
        "ಇಲ್ಲ",
        "ತಪ್ಪು",
        "nahi",
        "nahin",
        "नहीं",
        "गलत",
    }
    PARTIAL_MARKERS = {
        "but",
        "except",
        "only",
        "actually",
        "instead",
        "not exactly",
        "partly",
        "partial",
        "location is",
        "place is",
        "address is",
        "it was at",
        "wrong location",
        "wrong place",
        "लेकिन",
        "पर",
        "सिर्फ",
        "असल में",
        "स्थान",
        "जगह",
        "पता",
        "ಆದರೆ",
        "ಮಾತ್ರ",
        "ಸ್ಥಳ",
        "ವಿಳಾಸ",
        "ಜಾಗ",
    }

    CATEGORY_KEYWORDS: dict[str, set[str]] = {
        "theft": {
            "stolen",
            "steal",
            "theft",
            "robbed",
            "lost phone",
            "mobile lost",
            "phone lost",
            "mobile",
            "phone",
            "चोरी",
            "मोबाइल",
            "फोन",
            "ಕಳವು",
            "ಕಳ್ಳತನ",
            "ಮೊಬೈಲ್",
            "ಫೋನ್",
        },
        "accident": {
            "accident",
            "crash",
            "hit by",
            "collision",
            "दुर्घटना",
            "एक्सीडेंट",
            "अपघात",
            "ಅಪಘಾತ",
            "ಡಿಕ್ಕಿ",
        },
        "domestic": {
            "domestic",
            "husband",
            "wife",
            "violence",
            "beating",
            "abuse",
            "घर में मार",
            "पति",
            "पत्नी",
            "ಹಿಂಸೆ",
            "ಗಂಡ",
            "ಹೆಂಡತಿ",
            "ಹೊಡೆದ",
        },
        "cyber": {
            "cyber",
            "otp",
            "upi",
            "fraud",
            "scam",
            "bank account",
            "धोखा",
            "साइबर",
            "ವಂಚನೆ",
            "ಸೈಬರ್",
        },
        "noise": {
            "noise",
            "loud music",
            "speaker",
            "disturbance",
            "शोर",
            "तेज संगीत",
            "ಸದ್ದು",
            "ಶಬ್ದ",
        },
        "missing_person": {
            "missing",
            "not found",
            "kidnapped",
            "गुम",
            "लापता",
            "ಕಾಣೆಯಾಗಿದ್ದಾರೆ",
            "ಕಾಣೆಯಾಗಿದೆ",
        },
        "suspicious_activity": {
            "suspicious",
            "loitering",
            "following me",
            "unknown person",
            "संदिग्ध",
            "पीछा",
            "ಅನುಮಾನಾಸ್ಪದ",
            "ಹಿಂಬಾಲಿಸುತ್ತಿದ್ದಾರೆ",
        },
        "medical": {
            "ambulance",
            "injured",
            "bleeding",
            "unconscious",
            "heart attack",
            "एम्बुलेंस",
            "घायल",
            "बेहोश",
            "रक्त",
            "ಆಂಬ್ಯುಲೆನ್ಸ್",
            "ಗಾಯ",
            "ರಕ್ತ",
            "ಪ್ರಜ್ಞೆ",
        },
        "fire": {
            "fire",
            "burning",
            "smoke",
            "आग",
            "धुआं",
            "ಬೆಂಕಿ",
            "ಹೊಗೆ",
        },
        "traffic": {
            "traffic",
            "jam",
            "signal",
            "vehicle blocking",
            "जाम",
            "ट्रैफिक",
            "ಸಂಚಾರ",
            "ಟ್ರಾಫಿಕ್",
        },
    }

    DISTRESS_KEYWORDS = {
        "help",
        "urgent",
        "emergency",
        "danger",
        "attack",
        "kill",
        "dying",
        "blood",
        "bleeding",
        "unconscious",
        "fire",
        "ambulance",
        "मदद",
        "तुरंत",
        "आपात",
        "खतरा",
        "मार",
        "खून",
        "बचाओ",
        "सहाय",
        "ತುರ್ತು",
        "ಅಪಾಯ",
        "ರಕ್ತ",
        "ಸಾಯ",
        "ಉಳಿಸಿ",
        "ಬೆಂಕಿ",
    }

    LOW_CONFIDENCE_MARKERS = {
        "???",
        "unknown",
        "unclear",
        "can't explain",
        "cannot explain",
        "समझ नहीं",
        "ಗೊತ್ತಿಲ್ಲ",
    }

    async def analyze(self, text: str, call_state: CallState) -> CallAnalysis:
        lowered = text.strip().lower()
        language = self._detect_language(text, call_state)
        category = self._detect_category(lowered)
        confirmation_status, is_confirmation, correction_text, missing_fields = (
            self._detect_confirmation(lowered, text, call_state)
        )
        caller_wants_human = self._detect_human_request(lowered)
        urgency = self._score_urgency(lowered, category, caller_wants_human)
        sentiment = self._detect_sentiment(lowered, urgency)
        confidence = self._score_confidence(lowered, category, confirmation_status)
        summary = self._build_summary(text, category, confirmation_status, call_state)

        return CallAnalysis(
            language=language,
            dialect=self._detect_dialect(text, language),
            sentiment=sentiment,
            urgency=urgency,
            confidence=confidence,
            category=category,
            summary=summary,
            caller_wants_human=caller_wants_human,
            is_confirmation=is_confirmation,
            confirmation_status=confirmation_status,
            correction_text=correction_text,
            missing_fields=missing_fields,
            raw_text=text,
        )

    @staticmethod
    def _detect_language(text: str, call_state: CallState) -> str:
        if re.search(r"[\u0c80-\u0cff]", text):
            return "kannada"
        if re.search(r"[\u0900-\u097f]", text):
            return "hindi"
        if call_state.language in {"kannada", "hindi", "english"} and _word_count(text) <= 2:
            return call_state.language
        return "english"

    @staticmethod
    def _detect_dialect(text: str, language: str) -> str:
        lowered = text.lower()
        if language == "kannada":
            if any(word in text for word in {"ಮೈಸೂರು", "ಮಂಡ್ಯ"}):
                return "mysuru-mandya"
            if any(word in text for word in {"ಉತ್ತರ", "ಹುಬ್ಬಳ್ಳಿ", "ಧಾರವಾಡ"}):
                return "north-karnataka"
        if language == "hindi" and any(word in lowered for word in {"bhaiya", "humko", "hamko"}):
            return "north-indian-hindi"
        return ""

    def _detect_confirmation(
        self,
        text: str,
        original_text: str,
        call_state: CallState,
    ) -> tuple[str, bool | None, str, list[str]]:
        vachan_phases = {
            CallPhase.CONFIRMING.value,
            CallPhase.VACHAN_PENDING.value,
            CallPhase.VACHAN_PARTIAL.value,
        }
        if call_state.current_phase not in vachan_phases:
            return ConfirmationStatus.NONE.value, None, "", []
        words = set(re.findall(r"[\w\u0900-\u097f\u0c80-\u0cff]+", text.lower()))
        has_yes = bool(words & self.YES_WORDS or text in self.YES_WORDS)
        has_no = bool(words & self.NO_WORDS or text in self.NO_WORDS)
        has_partial = _contains_any(text, self.PARTIAL_MARKERS)
        correction_fields = self._detect_correction_fields(text)

        if has_partial or (has_yes and correction_fields) or (has_no and correction_fields):
            fields = correction_fields or ["description"]
            return ConfirmationStatus.PARTIAL.value, None, original_text.strip(), fields
        if has_yes:
            return ConfirmationStatus.YES.value, True, "", []
        if has_no:
            return ConfirmationStatus.NO.value, False, original_text.strip(), ["description"]
        if call_state.current_phase == CallPhase.VACHAN_PARTIAL.value and text.strip():
            fields = correction_fields or call_state.pending_clarification_fields or ["description"]
            return ConfirmationStatus.PARTIAL.value, None, original_text.strip(), fields
        if _word_count(text) >= 4:
            return ConfirmationStatus.PARTIAL.value, None, original_text.strip(), ["description"]
        return ConfirmationStatus.NONE.value, None, "", []

    @staticmethod
    def _detect_correction_fields(text: str) -> list[str]:
        fields: list[str] = []
        field_keywords = {
            "location": {
                "location",
                "place",
                "address",
                "where",
                "near",
                "at ",
                "bus stand",
                "railway",
                "station",
                "स्थान",
                "जगह",
                "पता",
                "पास",
                "ಸ್ಥಳ",
                "ವಿಳಾಸ",
                "ಹತ್ತಿರ",
                "ಬಸ್",
                "ನಿಲ್ದಾಣ",
            },
            "category": {
                "category",
                "issue type",
                "not theft",
                "accident",
                "fire",
                "fraud",
                "complaint type",
                "श्रेणी",
                "दुर्घटना",
                "आग",
                "ವರ್ಗ",
                "ಅಪಘಾತ",
                "ಬೆಂಕಿ",
            },
            "time": {
                "time",
                "today",
                "yesterday",
                "morning",
                "evening",
                "night",
                "समय",
                "आज",
                "कल",
                "ಬೆಳಗ್ಗೆ",
                "ಸಂಜೆ",
                "ರಾತ್ರಿ",
            },
            "description": {
                "summary",
                "details",
                "description",
                "what happened",
                "not exactly",
                "विवरण",
                "क्या हुआ",
                "ವಿವರ",
                "ಏನಾಯಿತು",
            },
        }
        for field, keywords in field_keywords.items():
            if _contains_any(text, keywords):
                fields.append(field)
        return fields

    def _detect_human_request(self, text: str) -> bool:
        return _contains_any(
            text,
            self.ENGLISH_HUMAN_REQUEST | self.HINDI_HUMAN_REQUEST | self.KANNADA_HUMAN_REQUEST,
        )

    def _detect_category(self, text: str) -> str:
        for category, keywords in self.CATEGORY_KEYWORDS.items():
            if _contains_any(text, keywords):
                return category
        return "general"

    def _score_urgency(self, text: str, category: str, caller_wants_human: bool) -> float:
        if category in {"fire", "medical"}:
            return 0.96
        if category in {"accident", "domestic", "missing_person"}:
            return 0.82
        if _contains_any(text, self.DISTRESS_KEYWORDS):
            return 0.92
        if caller_wants_human:
            return 0.65
        if category in {"theft", "cyber", "suspicious_activity"}:
            return 0.62
        if category in {"traffic", "noise"}:
            return 0.42
        return 0.5

    def _detect_sentiment(self, text: str, urgency: float) -> str:
        if urgency >= 0.9 or _contains_any(text, self.DISTRESS_KEYWORDS):
            return "distressed"
        if any(word in text for word in {"angry", "furious", "गुस्सा", "ಕೋಪ"}):
            return "angry"
        if any(word in text for word in {"afraid", "scared", "worried", "डर", "ಭಯ"}):
            return "anxious"
        return "calm"

    def _score_confidence(self, text: str, category: str, confirmation_status: str) -> float:
        if confirmation_status != ConfirmationStatus.NONE.value:
            return 0.96
        if not text.strip() or _word_count(text) <= 1:
            return 0.25
        if _contains_any(text, self.LOW_CONFIDENCE_MARKERS):
            return 0.25
        if category != "general":
            return 0.88
        if _word_count(text) >= 5:
            return 0.66
        return 0.42

    @staticmethod
    def _build_summary(
        text: str,
        category: str,
        confirmation_status: str,
        call_state: CallState,
    ) -> str:
        if confirmation_status == ConfirmationStatus.YES.value:
            return call_state.ai_summary or "Caller confirmed Sahayak's understanding."
        if confirmation_status == ConfirmationStatus.NO.value:
            return call_state.ai_summary or "Caller rejected Sahayak's understanding."
        if confirmation_status == ConfirmationStatus.PARTIAL.value:
            return call_state.ai_summary or "Caller partially corrected Sahayak's understanding."
        category_summaries = {
            "theft": "Caller reports theft or lost property.",
            "accident": "Caller reports an accident requiring assistance.",
            "domestic": "Caller reports a domestic safety concern.",
            "cyber": "Caller reports a cyber or financial fraud issue.",
            "noise": "Caller reports a noise disturbance.",
            "missing_person": "Caller reports a missing person concern.",
            "suspicious_activity": "Caller reports suspicious activity.",
            "medical": "Caller reports a medical emergency.",
            "fire": "Caller reports a fire emergency.",
            "traffic": "Caller reports a traffic issue.",
        }
        if category in category_summaries:
            return category_summaries[category]
        stripped = " ".join(text.strip().split())
        return stripped[:160] if stripped else "Caller issue was unclear."


class LLMAnalyzer:
    """LLM analyzer that asks for strict structured output."""

    def __init__(self, settings: Settings | None = None, client: Any | None = None):
        self.settings = settings or get_settings()
        self.client = client

    async def analyze(self, text: str, call_state: CallState) -> CallAnalysis:
        if not self.client:
            from openai import AsyncOpenAI

            self.client = AsyncOpenAI(
                api_key=self.settings.openai_api_key,
                base_url=self.settings.openai_base_url,
            )

        context = "\n".join(
            f"{item['role']}: {item['text']}" for item in call_state.transcript[-6:]
        )
        messages = [
            {"role": "system", "content": ANALYSIS_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Conversation so far:\n{context}\n\n"
                    f"Current phase: {call_state.current_phase}\n"
                    f"New caller message: {text!r}"
                ),
            },
        ]

        response_formats: list[dict[str, Any] | None] = [
            {
                "type": "json_schema",
                "json_schema": {
                    "name": "sahayak_call_analysis",
                    "strict": True,
                    "schema": CallAnalysis.model_json_schema(),
                },
            },
            {"type": "json_object"},
            None,
        ]

        last_error: Exception | None = None
        for response_format in response_formats:
            kwargs: dict[str, Any] = {
                "model": self.settings.llm_model,
                "messages": messages,
                "temperature": 0.1,
                "max_tokens": 350,
            }
            if response_format is not None:
                kwargs["response_format"] = response_format
            try:
                resp = await self.client.chat.completions.create(**kwargs)
                payload = extract_json(resp.choices[0].message.content or "{}")
                payload.setdefault("raw_text", text)
                analysis = CallAnalysis.model_validate(payload)
                return analysis
            except Exception as exc:
                last_error = exc
                if "429" in str(exc):
                    await asyncio.sleep(2)
                continue
        raise RuntimeError(f"LLM analysis failed: {last_error}")


async def analyze_call_utterance(
    text: str,
    call_state: CallState,
    settings: Settings | None = None,
    client: Any | None = None,
) -> CallAnalysis:
    """Analyze one utterance using configured provider with deterministic fallback."""

    cfg = settings or get_settings()
    provider = getattr(cfg, "analysis_provider", "auto").lower()

    if provider != "deterministic" and cfg.openai_api_key:
        try:
            return await LLMAnalyzer(settings=cfg, client=client).analyze(text, call_state)
        except Exception as exc:
            print(f"[WARN] LLM analysis fallback activated: {exc}")

    return await DeterministicAnalyzer().analyze(text, call_state)

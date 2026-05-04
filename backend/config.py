"""Runtime configuration for Sahayak 1092.

The app intentionally uses a small dataclass instead of a heavier settings
framework so local demos can run with only the existing requirements.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _as_int(value: str | None, default: int) -> int:
    if value is None or value == "":
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _as_float(value: str | None, default: float) -> float:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _as_csv(value: str | None, default: tuple[str, ...]) -> tuple[str, ...]:
    if not value:
        return default
    return tuple(item.strip() for item in value.split(",") if item.strip())


@dataclass(frozen=True)
class Settings:
    """Typed application settings loaded from environment variables."""

    app_name: str = "Sahayak 1092"
    app_version: str = "1.0.0"
    environment: str = "development"
    debug: bool = False
    demo_mode: bool = True

    host: str = "0.0.0.0"
    port: int = 8000
    base_url: str = "http://localhost:8000"
    cors_origins: tuple[str, ...] = ("*",)

    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_phone_number: str = "+18666212451"
    transfer_mode: str = "mock"

    openai_api_key: str = ""
    openai_base_url: str | None = None
    llm_model: str = "gpt-4o"
    analysis_provider: str = "auto"
    embedding_provider: str = "deterministic"
    embedding_model: str = "text-embedding-3-small"
    embedding_dimension: int = 1536
    vector_search_limit: int = 10
    vector_db_match_threshold: float = 0.15

    bhashini_api_key: str = ""
    bhashini_user_id: str = ""
    bhashini_pipeline_url: str = "https://dhruva-api.bhashini.gov.in/services/inference"
    deepgram_api_key: str = ""
    gemini_api_key: str = ""
    stt_provider_order: tuple[str, ...] = (
        "bhashini",
        "deepgram",
        "google",
        "openai_whisper",
    )
    tts_provider_order: tuple[str, ...] = (
        "bhashini",
        "google",
        "edge",
        "openai",
    )
    voice_provider_timeout_sec: float = 12.0
    tts_phrase_cache_enabled: bool = True

    supabase_url: str = ""
    supabase_key: str = ""
    redis_url: str = ""

    low_confidence_threshold: float = 0.5
    low_confidence_max_attempts: int = 2
    autonomous_confidence_threshold: float = 0.7
    similarity_confidence_threshold: float = 0.6
    similarity_match_threshold: float = 0.7
    extreme_urgency_threshold: float = 0.9
    high_help_alert_timeout_sec: int = 120
    high_help_alert_demo_timeout_sec: int = 20
    vad_silence_threshold: float = 0.02
    vad_silence_duration_ms: int = 1500
    vad_buffer_max_duration_ms: int = 15000

    @property
    def ws_base_url(self) -> str:
        return self.base_url.replace("https://", "wss://").replace("http://", "ws://")

    @property
    def twilio_configured(self) -> bool:
        return bool(self.twilio_account_sid and self.twilio_auth_token and self.twilio_phone_number)

    @property
    def supabase_configured(self) -> bool:
        return bool(self.supabase_url and self.supabase_key)

    @property
    def effective_high_help_alert_timeout_sec(self) -> int:
        return self.high_help_alert_demo_timeout_sec if self.demo_mode else self.high_help_alert_timeout_sec


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached settings from the current process environment."""

    return Settings(
        environment=os.getenv("SAHAYAK_ENV", os.getenv("ENVIRONMENT", "development")),
        debug=_as_bool(os.getenv("DEBUG"), False),
        demo_mode=_as_bool(os.getenv("DEMO_MODE"), True),
        host=os.getenv("HOST", "0.0.0.0"),
        port=_as_int(os.getenv("PORT"), 8000),
        base_url=os.getenv("BASE_URL", "http://localhost:8000"),
        cors_origins=_as_csv(os.getenv("CORS_ORIGINS"), ("*",)),
        twilio_account_sid=os.getenv("TWILIO_ACCOUNT_SID", ""),
        twilio_auth_token=os.getenv("TWILIO_AUTH_TOKEN", ""),
        twilio_phone_number=os.getenv("TWILIO_PHONE_NUMBER", "+18666212451"),
        transfer_mode=os.getenv("TRANSFER_MODE", "mock"),
        openai_api_key=os.getenv("OPENAI_API_KEY", ""),
        openai_base_url=os.getenv("OPENAI_BASE_URL") or None,
        llm_model=os.getenv("LLM_MODEL", "gpt-4o"),
        analysis_provider=os.getenv("ANALYSIS_PROVIDER", "auto"),
        embedding_provider=os.getenv("EMBEDDING_PROVIDER", "deterministic"),
        embedding_model=os.getenv("EMBEDDING_MODEL", "text-embedding-3-small"),
        embedding_dimension=_as_int(os.getenv("EMBEDDING_DIMENSION"), 1536),
        vector_search_limit=_as_int(os.getenv("VECTOR_SEARCH_LIMIT"), 10),
        vector_db_match_threshold=_as_float(os.getenv("VECTOR_DB_MATCH_THRESHOLD"), 0.15),
        bhashini_api_key=os.getenv("BHASHINI_API_KEY", ""),
        bhashini_user_id=os.getenv("BHASHINI_USER_ID", ""),
        bhashini_pipeline_url=os.getenv(
            "BHASHINI_PIPELINE_URL",
            "https://dhruva-api.bhashini.gov.in/services/inference",
        ),
        deepgram_api_key=os.getenv("DEEPGRAM_API_KEY", ""),
        gemini_api_key=os.getenv("GEMINI_API_KEY", ""),
        stt_provider_order=_as_csv(
            os.getenv("STT_PROVIDER_ORDER"),
            ("bhashini", "deepgram", "google", "openai_whisper"),
        ),
        tts_provider_order=_as_csv(
            os.getenv("TTS_PROVIDER_ORDER"),
            ("bhashini", "google", "edge", "openai"),
        ),
        voice_provider_timeout_sec=_as_float(os.getenv("VOICE_PROVIDER_TIMEOUT_SEC"), 12.0),
        tts_phrase_cache_enabled=_as_bool(
            os.getenv("TTS_PHRASE_CACHE_ENABLED", os.getenv("PREGENERATED_TTS_ENABLED")),
            True,
        ),
        supabase_url=os.getenv("SUPABASE_URL", ""),
        supabase_key=os.getenv("SUPABASE_KEY", ""),
        redis_url=os.getenv("REDIS_URL", ""),
        low_confidence_threshold=_as_float(os.getenv("LOW_CONFIDENCE_THRESHOLD"), 0.5),
        low_confidence_max_attempts=_as_int(os.getenv("LOW_CONFIDENCE_MAX_ATTEMPTS"), 2),
        autonomous_confidence_threshold=_as_float(os.getenv("AUTONOMOUS_CONFIDENCE_THRESHOLD"), 0.7),
        similarity_confidence_threshold=_as_float(os.getenv("SIMILARITY_CONFIDENCE_THRESHOLD"), 0.6),
        similarity_match_threshold=_as_float(os.getenv("SIMILARITY_MATCH_THRESHOLD"), 0.7),
        extreme_urgency_threshold=_as_float(os.getenv("EXTREME_URGENCY_THRESHOLD"), 0.9),
        high_help_alert_timeout_sec=_as_int(os.getenv("HIGH_HELP_ALERT_TIMEOUT_SEC"), 120),
        high_help_alert_demo_timeout_sec=_as_int(os.getenv("HIGH_HELP_ALERT_DEMO_TIMEOUT_SEC"), 20),
        vad_silence_threshold=_as_float(os.getenv("VAD_SILENCE_THRESHOLD"), 0.02),
        vad_silence_duration_ms=_as_int(os.getenv("VAD_SILENCE_DURATION_MS"), 1500),
        vad_buffer_max_duration_ms=_as_int(os.getenv("VAD_BUFFER_MAX_DURATION_MS"), 15000),
    )

"""Speech-to-text provider cascade for the Twilio voice pipeline."""

from __future__ import annotations

import asyncio
import base64
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import httpx

from backend.config import Settings, get_settings
from backend.voice.audio_codec import create_wav_header


LANGUAGE_TO_BHASHINI = {
    "kannada": "kn",
    "hindi": "hi",
    "english": "en",
    "telugu": "te",
    "tamil": "ta",
    "urdu": "ur",
    "kn": "kn",
    "hi": "hi",
    "en": "en",
}

LANGUAGE_TO_DEEPGRAM = {
    "kannada": "kn",
    "hindi": "hi",
    "english": "en",
    "telugu": "te",
    "tamil": "ta",
    "urdu": "ur",
    "kn": "kn",
    "hi": "hi",
    "en": "en",
}

LANGUAGE_TO_GOOGLE = {
    "kannada": "kn-IN",
    "hindi": "hi-IN",
    "english": "en-IN",
    "telugu": "te-IN",
    "tamil": "ta-IN",
    "urdu": "ur-IN",
}


def is_valid_key(key: str | None) -> bool:
    """Return true for real-looking credentials and false for placeholders."""

    if not key:
        return False
    stripped = key.strip()
    return bool(stripped) and not stripped.startswith("your_")


def _language_key(language: str | None) -> str:
    return (language or "english").strip().lower()


def _timed_ms(started_at: float) -> float:
    return round((time.perf_counter() - started_at) * 1000, 2)


def _stt_name(name: str) -> str:
    return name.strip().lower().replace("-", "_")


@dataclass(frozen=True)
class STTAttempt:
    """One provider attempt in the STT cascade."""

    provider: str
    configured: bool
    success: bool
    latency_ms: float
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "configured": self.configured,
            "success": self.success,
            "latency_ms": self.latency_ms,
            "error": self.error,
        }


@dataclass(frozen=True)
class STTResult:
    """Result returned by the STT cascade."""

    text: str | None
    provider: str | None
    latency_ms: float
    attempts: list[STTAttempt]

    @property
    def success(self) -> bool:
        return bool(self.text)

    def as_event_payload(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "provider": self.provider,
            "latency_ms": self.latency_ms,
            "attempts": [attempt.as_dict() for attempt in self.attempts],
            "success": self.success,
        }


class STTProvider(Protocol):
    """Provider contract for raw 8kHz PCM16 caller audio."""

    name: str

    def is_configured(self) -> bool:
        """Return true when the provider has enough configuration to run."""

    async def transcribe(self, audio_bytes: bytes, language: str) -> str | None:
        """Transcribe audio bytes into text."""


@dataclass
class BhashiniSTTProvider:
    """Bhashini/Dhruva ASR provider for Indian-language helpline calls."""

    settings: Settings
    name: str = "bhashini"

    def is_configured(self) -> bool:
        return is_valid_key(self.settings.bhashini_api_key) and bool(self.settings.bhashini_pipeline_url)

    async def transcribe(self, audio_bytes: bytes, language: str) -> str | None:
        wav_data = create_wav_header(audio_bytes) + audio_bytes
        audio_base64 = base64.b64encode(wav_data).decode("utf-8")
        src_lang = LANGUAGE_TO_BHASHINI.get(_language_key(language), "kn")
        payload = {
            "pipelineTasks": [
                {
                    "taskType": "asr",
                    "config": {
                        "language": {"sourceLanguage": src_lang},
                        "audioFormat": "wav",
                        "samplingRate": 8000,
                    },
                }
            ],
            "inputData": {"audio": [{"audioContent": audio_base64}]},
        }
        headers = {
            "Authorization": self.settings.bhashini_api_key,
            "Content-Type": "application/json",
        }
        if self.settings.bhashini_user_id:
            headers["userID"] = self.settings.bhashini_user_id

        async with httpx.AsyncClient(timeout=self.settings.voice_provider_timeout_sec) as client:
            response = await client.post(
                self.settings.bhashini_pipeline_url,
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
            data = response.json()

        pipeline_response = data.get("pipelineResponse", [{}])
        if not pipeline_response:
            return None
        texts = pipeline_response[0].get("output", [{}])
        if not texts:
            return None
        text = str(texts[0].get("source") or "").strip()
        return text or None


@dataclass
class DeepgramSTTProvider:
    """Deepgram Nova fallback for fast multilingual transcription."""

    settings: Settings
    name: str = "deepgram"

    def is_configured(self) -> bool:
        return is_valid_key(self.settings.deepgram_api_key)

    async def transcribe(self, audio_bytes: bytes, language: str) -> str | None:
        wav_data = create_wav_header(audio_bytes) + audio_bytes
        language_code = LANGUAGE_TO_DEEPGRAM.get(_language_key(language), "hi")
        headers = {
            "Authorization": f"Token {self.settings.deepgram_api_key}",
            "Content-Type": "audio/wav",
        }
        url = (
            "https://api.deepgram.com/v1/listen"
            f"?model=nova-2&language={language_code}&smart_format=true"
        )
        async with httpx.AsyncClient(timeout=self.settings.voice_provider_timeout_sec) as client:
            response = await client.post(url, content=wav_data, headers=headers)
            response.raise_for_status()
            data = response.json()
        transcript = (
            data.get("results", {})
            .get("channels", [{}])[0]
            .get("alternatives", [{}])[0]
            .get("transcript", "")
        )
        transcript = str(transcript).strip()
        return transcript or None


@dataclass
class GoogleCloudSTTProvider:
    """Google Cloud Speech-to-Text REST fallback using the configured Google key."""

    settings: Settings
    name: str = "google"

    def is_configured(self) -> bool:
        return is_valid_key(self.settings.gemini_api_key)

    async def transcribe(self, audio_bytes: bytes, language: str) -> str | None:
        language_code = LANGUAGE_TO_GOOGLE.get(_language_key(language), "en-IN")
        payload = {
            "config": {
                "encoding": "LINEAR16",
                "sampleRateHertz": 8000,
                "languageCode": language_code,
            },
            "audio": {"content": base64.b64encode(audio_bytes).decode("utf-8")},
        }
        async with httpx.AsyncClient(timeout=self.settings.voice_provider_timeout_sec) as client:
            response = await client.post(
                f"https://speech.googleapis.com/v1/speech:recognize?key={self.settings.gemini_api_key}",
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
        results = data.get("results", [])
        if not results:
            return None
        transcript = results[0].get("alternatives", [{}])[0].get("transcript", "")
        transcript = str(transcript).strip()
        return transcript or None


@dataclass
class OpenAIWhisperSTTProvider:
    """OpenAI Whisper fallback for batch transcription."""

    settings: Settings
    name: str = "openai_whisper"

    def is_configured(self) -> bool:
        return is_valid_key(self.settings.openai_api_key) and self.settings.openai_api_key.startswith("sk-")

    async def transcribe(self, audio_bytes: bytes, language: str) -> str | None:
        from openai import AsyncOpenAI
        import tempfile

        wav_data = create_wav_header(audio_bytes) + audio_bytes
        temp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
                temp_file.write(wav_data)
                temp_file.flush()
                temp_path = Path(temp_file.name)

            client = AsyncOpenAI(api_key=self.settings.openai_api_key)
            with temp_path.open("rb") as audio_file:
                response = await client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    language=None,
                )
            text = str(response.text or "").strip()
            return text or None
        finally:
            if temp_path:
                temp_path.unlink(missing_ok=True)


def build_stt_providers(settings: Settings | None = None) -> dict[str, STTProvider]:
    """Build all production STT providers keyed by config name."""

    active_settings = settings or get_settings()
    providers: list[STTProvider] = [
        BhashiniSTTProvider(active_settings),
        DeepgramSTTProvider(active_settings),
        GoogleCloudSTTProvider(active_settings),
        OpenAIWhisperSTTProvider(active_settings),
    ]
    return {provider.name: provider for provider in providers}


def ordered_stt_providers(
    settings: Settings | None = None,
    providers: list[STTProvider] | None = None,
) -> list[STTProvider]:
    """Return providers in the configured order, or a supplied test order."""

    if providers is not None:
        return providers
    active_settings = settings or get_settings()
    available = build_stt_providers(active_settings)
    ordered: list[STTProvider] = []
    for name in active_settings.stt_provider_order:
        provider = available.get(_stt_name(name))
        if provider:
            ordered.append(provider)
    return ordered


async def transcribe_audio_with_fallback(
    audio_bytes: bytes,
    language: str = "english",
    *,
    settings: Settings | None = None,
    providers: list[STTProvider] | None = None,
) -> STTResult:
    """Run STT providers in order until one returns non-empty text."""

    active_settings = settings or get_settings()
    total_started_at = time.perf_counter()
    attempts: list[STTAttempt] = []

    if not audio_bytes:
        return STTResult(
            text=None,
            provider=None,
            latency_ms=_timed_ms(total_started_at),
            attempts=[
                STTAttempt(
                    provider="input",
                    configured=True,
                    success=False,
                    latency_ms=0.0,
                    error="empty_audio",
                )
            ],
        )

    for provider in ordered_stt_providers(active_settings, providers):
        provider_name = getattr(provider, "name", provider.__class__.__name__)
        configured_checker = getattr(provider, "is_configured", None)
        configured = configured_checker() if callable(configured_checker) else True
        if not configured:
            attempts.append(
                STTAttempt(
                    provider=provider_name,
                    configured=False,
                    success=False,
                    latency_ms=0.0,
                    error="not_configured",
                )
            )
            continue

        started_at = time.perf_counter()
        try:
            text = await asyncio.wait_for(
                provider.transcribe(audio_bytes, language),
                timeout=active_settings.voice_provider_timeout_sec,
            )
            latency_ms = _timed_ms(started_at)
            clean_text = str(text or "").strip()
            attempts.append(
                STTAttempt(
                    provider=provider_name,
                    configured=True,
                    success=bool(clean_text),
                    latency_ms=latency_ms,
                    error=None if clean_text else "empty_transcript",
                )
            )
            if clean_text:
                return STTResult(
                    text=clean_text,
                    provider=provider_name,
                    latency_ms=_timed_ms(total_started_at),
                    attempts=attempts,
                )
        except Exception as exc:
            attempts.append(
                STTAttempt(
                    provider=provider_name,
                    configured=True,
                    success=False,
                    latency_ms=_timed_ms(started_at),
                    error=exc.__class__.__name__,
                )
            )

    return STTResult(
        text=None,
        provider=None,
        latency_ms=_timed_ms(total_started_at),
        attempts=attempts,
    )


async def transcribe_audio(audio_bytes: bytes, language: str = "english") -> str | None:
    """Compatibility wrapper returning only transcript text."""

    result = await transcribe_audio_with_fallback(audio_bytes, language)
    return result.text

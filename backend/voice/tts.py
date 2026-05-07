"""Text-to-speech provider cascade and common phrase cache."""

from __future__ import annotations

import asyncio
import base64
import io
import math
import time
import wave
from dataclasses import dataclass, field
from threading import RLock
from typing import Any, Protocol

import httpx

from backend.config import Settings, get_settings
from backend.voice.audio_codec import MULAW_SAMPLE_RATE, pcm16_to_mulaw
from backend.voice.stt import is_valid_key


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

LANGUAGE_TO_SARVAM = {
    "kannada": "kn-IN",
    "hindi": "hi-IN",
    "english": "en-IN",
    "telugu": "te-IN",
    "tamil": "ta-IN",
    "bengali": "bn-IN",
    "malayalam": "ml-IN",
    "marathi": "mr-IN",
    "odia": "od-IN",
    "punjabi": "pa-IN",
    "gujarati": "gu-IN",
    "urdu": "ur-IN",
    "kn": "kn-IN",
    "hi": "hi-IN",
    "en": "en-IN",
}

# Per-language natural speaker mapping for Sarvam Bulbul TTS
# Female voices: pavithra (hi/en), anushka (kn), maitreyi (te/mr/bn)
# Override globally via SARVAM_TTS_SPEAKER env var
SARVAM_SPEAKER_MAP = {
    "hindi":     "pavithra",   # warm, natural Hindi female
    "english":   "pavithra",   # English-accented Indian female
    "kannada":   "anushka",    # Kannada female
    "telugu":    "maitreyi",   # Telugu female
    "tamil":     "maitreyi",   # Tamil female
    "bengali":   "maitreyi",   # Bengali fallback
    "marathi":   "maitreyi",   # Marathi fallback
    "gujarati":  "pavithra",
    "punjabi":   "pavithra",
    "malayalam": "anushka",
    "odia":      "maitreyi",
    "urdu":      "pavithra",
}

GOOGLE_VOICES = {
    "kannada":   ("kn-IN", "kn-IN-Wavenet-A"),
    "hindi":     ("hi-IN", "hi-IN-Wavenet-D"),   # female, natural
    "english":   ("en-IN", "en-IN-Wavenet-D"),
    "telugu":    ("te-IN", "te-IN-Standard-A"),
    "tamil":     ("ta-IN", "ta-IN-Wavenet-C"),
    "urdu":      ("ur-IN", "ur-IN-Wavenet-A"),
    "bengali":   ("bn-IN", "bn-IN-Wavenet-A"),
    "malayalam": ("ml-IN", "ml-IN-Wavenet-A"),
    "marathi":   ("mr-IN", "mr-IN-Wavenet-A"),
    "gujarati":  ("gu-IN", "gu-IN-Wavenet-A"),
    "punjabi":   ("pa-IN", "pa-IN-Standard-A"),
}

EDGE_VOICES = {
    "kannada":   "kn-IN-GaganNeural",
    "hindi":     "hi-IN-SwaraNeural",    # warm, clear female Hindi
    "english":   "en-IN-NeerjaNeural",
    "telugu":    "te-IN-ShrutiNeural",
    "tamil":     "ta-IN-PallaviNeural",
    "urdu":      "ur-PK-UzmaNeural",     # female Urdu
    "bengali":   "bn-IN-TanishaaNeural",
    "malayalam": "ml-IN-SobhanaNeural",
    "marathi":   "mr-IN-AarohiNeural",
    "gujarati":  "gu-IN-DhwaniNeural",
    "punjabi":   "pa-IN-VaaniNeural",
}

COMMON_TTS_PHRASES = {
    "english": {
        "Please say yes or no.",
        "One moment please.",
        "Thank you.",
        "Please describe what was wrong.",
        "Connecting you to the closest officer who speaks like you. Just a moment.",
        "Redirecting you to Police now. Please hold.",
        "Redirecting you to Ambulance now. Please hold.",
        "Redirecting you to Fire Services now. Please hold.",
    },
    "hindi": {
        "कृपया हाँ या नहीं कहें.",
        "कृपया एक क्षण प्रतीक्षा करें.",
        "धन्यवाद.",
        "कृपया बताइए कि क्या गलत था.",
    },
    "kannada": {
        "ದಯವಿಟ್ಟು ಹೌದು ಅಥವಾ ಇಲ್ಲ ಎಂದು ಹೇಳಿ.",
        "ದಯವಿಟ್ಟು ಒಂದು ಕ್ಷಣ ಕಾಯಿರಿ.",
        "ಧನ್ಯವಾದಗಳು.",
        "ದಯವಿಟ್ಟು ಏನು ತಪ್ಪಾಗಿದೆ ಎಂದು ಹೇಳಿ.",
    },
}


def _language_key(language: str | None) -> str:
    return (language or "english").strip().lower()


def _tts_name(name: str) -> str:
    return name.strip().lower().replace("-", "_")


def _timed_ms(started_at: float) -> float:
    return round((time.perf_counter() - started_at) * 1000, 2)


def _wav_to_pcm16(raw_audio: bytes) -> bytes:
    if raw_audio[:4] != b"RIFF":
        return raw_audio
    try:
        with wave.open(io.BytesIO(raw_audio)) as wav_file:
            return wav_file.readframes(wav_file.getnframes())
    except Exception:
        return raw_audio[44:]


def _resample_pcm16(pcm_bytes: bytes, source_rate: int, target_rate: int = MULAW_SAMPLE_RATE) -> bytes:
    if source_rate == target_rate:
        return pcm_bytes
    import audioop

    converted, _ = audioop.ratecv(pcm_bytes, 2, 1, source_rate, target_rate, None)
    return converted


def _tone_pcm16(duration_ms: int = 650, frequency_hz: int = 660) -> bytes:
    total_samples = int(MULAW_SAMPLE_RATE * duration_ms / 1000)
    amplitude = 8500
    samples = bytearray()
    for index in range(total_samples):
        value = int(amplitude * math.sin(2 * math.pi * frequency_hz * index / MULAW_SAMPLE_RATE))
        samples.extend(value.to_bytes(2, "little", signed=True))
    return bytes(samples)


@dataclass(frozen=True)
class TTSAttempt:
    """One provider attempt in the TTS cascade."""

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
class TTSResult:
    """Telephony-ready TTS result."""

    audio: bytes | None
    provider: str | None
    latency_ms: float
    attempts: list[TTSAttempt]
    from_cache: bool = False
    fallback_tone: bool = False

    @property
    def success(self) -> bool:
        return bool(self.audio)

    def as_event_payload(self, *, text: str | None = None, language: str | None = None) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "latency_ms": self.latency_ms,
            "attempts": [attempt.as_dict() for attempt in self.attempts],
            "from_cache": self.from_cache,
            "fallback_tone": self.fallback_tone,
            "success": self.success,
            "audio_bytes": len(self.audio or b""),
            "language": language,
            "text_preview": text[:120] if text else None,
        }


@dataclass
class PhraseAudioCache:
    """In-memory cache for common Vachan and routing phrases."""

    common_phrases: dict[str, set[str]] = field(default_factory=lambda: COMMON_TTS_PHRASES)

    def __post_init__(self) -> None:
        self._lock = RLock()
        self._audio: dict[tuple[str, str], bytes] = {}

    @staticmethod
    def _normalise_text(text: str) -> str:
        return " ".join(text.strip().split())

    def key(self, text: str, language: str) -> tuple[str, str]:
        return (_language_key(language), self._normalise_text(text))

    def is_common(self, text: str, language: str) -> bool:
        language_key = _language_key(language)
        normalised = self._normalise_text(text)
        return normalised in {self._normalise_text(item) for item in self.common_phrases.get(language_key, set())}

    def get(self, text: str, language: str) -> bytes | None:
        with self._lock:
            return self._audio.get(self.key(text, language))

    def set(self, text: str, language: str, audio: bytes) -> None:
        if not audio:
            return
        with self._lock:
            self._audio[self.key(text, language)] = audio

    def stats(self) -> dict[str, int]:
        with self._lock:
            return {"cached_phrases": len(self._audio)}


phrase_audio_cache = PhraseAudioCache()


class TTSProvider(Protocol):
    """Provider contract returning raw 8kHz PCM16 audio."""

    name: str

    def is_configured(self) -> bool:
        """Return true when the provider has enough configuration to run."""

    async def synthesize(self, text: str, language: str) -> bytes | None:
        """Synthesize text into raw 8kHz PCM16 audio bytes."""


@dataclass
class SarvamTTSProvider:
    """Sarvam Bulbul TTS provider for natural Indian-language responses."""

    settings: Settings
    name: str = "sarvam"

    def is_configured(self) -> bool:
        return is_valid_key(self.settings.sarvam_api_key) and bool(self.settings.sarvam_base_url)

    async def synthesize(self, text: str, language: str) -> bytes | None:
        lang_key = _language_key(language)
        language_code = LANGUAGE_TO_SARVAM.get(lang_key, "en-IN")
        # Pick natural female speaker per language; fall back to env config
        speaker = SARVAM_SPEAKER_MAP.get(lang_key, self.settings.sarvam_tts_speaker)
        payload = {
            "text": text[:2500],
            "target_language_code": language_code,
            "model": self.settings.sarvam_tts_model,
            "speaker": speaker,
            "speech_sample_rate": 8000,
            "output_audio_codec": "wav",
        }
        if self.settings.sarvam_tts_model == "bulbul:v3":
            payload["pace"] = self.settings.sarvam_tts_pace
            payload["temperature"] = self.settings.sarvam_tts_temperature

        async with httpx.AsyncClient(timeout=self.settings.voice_provider_timeout_sec) as client:
            response = await client.post(
                f"{self.settings.sarvam_base_url.rstrip('/')}/text-to-speech",
                json=payload,
                headers={
                    "api-subscription-key": self.settings.sarvam_api_key,
                    "Content-Type": "application/json",
                },
            )
            response.raise_for_status()
            data = response.json()

        audios = data.get("audios") or []
        if not audios:
            return None
        return _wav_to_pcm16(base64.b64decode(audios[0]))


@dataclass
class BhashiniTTSProvider:
    """Bhashini/Dhruva TTS provider for Indian-language responses."""

    settings: Settings
    name: str = "bhashini"

    def is_configured(self) -> bool:
        return is_valid_key(self.settings.bhashini_api_key) and bool(self.settings.bhashini_pipeline_url)

    async def synthesize(self, text: str, language: str) -> bytes | None:
        src_lang = LANGUAGE_TO_BHASHINI.get(_language_key(language), "kn")
        payload = {
            "pipelineTasks": [
                {
                    "taskType": "tts",
                    "config": {
                        "language": {"sourceLanguage": src_lang},
                        "gender": "female",
                        "samplingRate": 8000,
                    },
                }
            ],
            "inputData": {"input": [{"source": text}]},
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
        audios = pipeline_response[0].get("audio", [{}])
        if not audios:
            return None
        audio_base64 = audios[0].get("audioContent", "")
        if not audio_base64:
            return None
        return _wav_to_pcm16(base64.b64decode(audio_base64))


@dataclass
class GoogleCloudTTSProvider:
    """Google Cloud Text-to-Speech REST fallback."""

    settings: Settings
    name: str = "google"

    def is_configured(self) -> bool:
        return is_valid_key(self.settings.gemini_api_key)

    async def synthesize(self, text: str, language: str) -> bytes | None:
        lang_code, voice_name = GOOGLE_VOICES.get(
            _language_key(language),
            ("en-IN", "en-IN-Wavenet-A"),
        )
        payload = {
            "input": {"text": text},
            "voice": {
                "languageCode": lang_code,
                "name": voice_name,
                "ssmlGender": "FEMALE",
            },
            "audioConfig": {
                "audioEncoding": "LINEAR16",
                "sampleRateHertz": 8000,
            },
        }
        async with httpx.AsyncClient(timeout=self.settings.voice_provider_timeout_sec) as client:
            response = await client.post(
                f"https://texttospeech.googleapis.com/v1/text:synthesize?key={self.settings.gemini_api_key}",
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        audio_base64 = data.get("audioContent", "")
        if not audio_base64:
            return None
        return _wav_to_pcm16(base64.b64decode(audio_base64))


@dataclass
class EdgeTTSProvider:
    """Microsoft Edge TTS no-key fallback for local demos."""

    settings: Settings
    name: str = "edge"

    def is_configured(self) -> bool:
        return True

    async def synthesize(self, text: str, language: str) -> bytes | None:
        import edge_tts

        voice = EDGE_VOICES.get(_language_key(language), "en-IN-NeerjaNeural")
        communicate = edge_tts.Communicate(
            text,
            voice,
            rate="-5%",
            connect_timeout=int(self.settings.voice_provider_timeout_sec),
            receive_timeout=max(int(self.settings.voice_provider_timeout_sec), 10),
        )
        audio_bytes = b""
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_bytes += chunk["data"]

        if not audio_bytes:
            return None

        if audio_bytes[:4] == b"RIFF":
            return _resample_pcm16(_wav_to_pcm16(audio_bytes), 16000)

        try:
            from pydub import AudioSegment

            decoded = AudioSegment.from_mp3(io.BytesIO(audio_bytes))
            decoded = decoded.set_frame_rate(MULAW_SAMPLE_RATE).set_channels(1).set_sample_width(2)
            return decoded.raw_data
        except Exception:
            return None


@dataclass
class OpenAITTSProvider:
    """OpenAI TTS fallback, resampled to telephony PCM before mu-law encoding."""

    settings: Settings
    name: str = "openai"

    def is_configured(self) -> bool:
        return is_valid_key(self.settings.openai_api_key) and self.settings.openai_api_key.startswith("sk-")

    async def synthesize(self, text: str, language: str) -> bytes | None:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=self.settings.openai_api_key)
        response = await client.audio.speech.create(
            model="tts-1",
            voice="nova",
            input=text,
            response_format="pcm",
            speed=0.95,
        )
        pcm_24k = bytes(response.content)
        return _resample_pcm16(pcm_24k, 24000)


@dataclass
class AudibleFallbackToneProvider:
    """Final guardrail so Twilio never receives silence after TTS failure."""

    settings: Settings
    name: str = "fallback_tone"

    def is_configured(self) -> bool:
        return True

    async def synthesize(self, text: str, language: str) -> bytes | None:
        return _tone_pcm16()


def build_tts_providers(settings: Settings | None = None) -> dict[str, TTSProvider]:
    """Build all production TTS providers keyed by config name."""

    active_settings = settings or get_settings()
    providers: list[TTSProvider] = [
        SarvamTTSProvider(active_settings),
        BhashiniTTSProvider(active_settings),
        GoogleCloudTTSProvider(active_settings),
        EdgeTTSProvider(active_settings),
        OpenAITTSProvider(active_settings),
    ]
    return {provider.name: provider for provider in providers}


def ordered_tts_providers(
    settings: Settings | None = None,
    providers: list[TTSProvider] | None = None,
) -> list[TTSProvider]:
    """Return providers in the configured order, or a supplied test order."""

    if providers is not None:
        return providers
    active_settings = settings or get_settings()
    available = build_tts_providers(active_settings)
    ordered: list[TTSProvider] = []
    for name in active_settings.tts_provider_order:
        provider = available.get(_tts_name(name))
        if provider:
            ordered.append(provider)
    return ordered


async def warm_common_phrase_cache(
    language: str = "english",
    *,
    settings: Settings | None = None,
    providers: list[TTSProvider] | None = None,
    cache: PhraseAudioCache | None = None,
) -> dict[str, int]:
    """Pre-synthesize configured common phrases into the in-memory cache."""

    active_cache = cache or phrase_audio_cache
    phrases = active_cache.common_phrases.get(_language_key(language), set())
    warmed = 0
    for phrase in phrases:
        result = await synthesize_speech_with_fallback(
            phrase,
            language,
            settings=settings,
            providers=providers,
            cache=active_cache,
        )
        if result.success:
            warmed += 1
    return {"attempted": len(phrases), "warmed": warmed}


async def synthesize_speech_with_fallback(
    text: str,
    language: str = "english",
    *,
    settings: Settings | None = None,
    providers: list[TTSProvider] | None = None,
    cache: PhraseAudioCache | None = None,
) -> TTSResult:
    """Run TTS providers in order, returning mu-law audio for Twilio."""

    active_settings = settings or get_settings()
    active_cache = cache or phrase_audio_cache
    total_started_at = time.perf_counter()
    attempts: list[TTSAttempt] = []
    clean_text = " ".join((text or "").strip().split())

    if not clean_text:
        return TTSResult(
            audio=None,
            provider=None,
            latency_ms=_timed_ms(total_started_at),
            attempts=[
                TTSAttempt(
                    provider="input",
                    configured=True,
                    success=False,
                    latency_ms=0.0,
                    error="empty_text",
                )
            ],
        )

    if active_settings.tts_phrase_cache_enabled:
        cached_audio = active_cache.get(clean_text, language)
        if cached_audio:
            return TTSResult(
                audio=cached_audio,
                provider="phrase_cache",
                latency_ms=_timed_ms(total_started_at),
                attempts=[
                    TTSAttempt(
                        provider="phrase_cache",
                        configured=True,
                        success=True,
                        latency_ms=0.0,
                    )
                ],
                from_cache=True,
            )

    for provider in ordered_tts_providers(active_settings, providers):
        provider_name = getattr(provider, "name", provider.__class__.__name__)
        configured_checker = getattr(provider, "is_configured", None)
        configured = configured_checker() if callable(configured_checker) else True
        if not configured:
            attempts.append(
                TTSAttempt(
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
            pcm_audio = await asyncio.wait_for(
                provider.synthesize(clean_text, language),
                timeout=active_settings.voice_provider_timeout_sec,
            )
            latency_ms = _timed_ms(started_at)
            if pcm_audio:
                mulaw_audio = pcm16_to_mulaw(pcm_audio)
                attempts.append(
                    TTSAttempt(
                        provider=provider_name,
                        configured=True,
                        success=True,
                        latency_ms=latency_ms,
                    )
                )
                if active_settings.tts_phrase_cache_enabled and active_cache.is_common(clean_text, language):
                    active_cache.set(clean_text, language, mulaw_audio)
                return TTSResult(
                    audio=mulaw_audio,
                    provider=provider_name,
                    latency_ms=_timed_ms(total_started_at),
                    attempts=attempts,
                )
            attempts.append(
                TTSAttempt(
                    provider=provider_name,
                    configured=True,
                    success=False,
                    latency_ms=latency_ms,
                    error="empty_audio",
                )
            )
        except Exception as exc:
            attempts.append(
                TTSAttempt(
                    provider=provider_name,
                    configured=True,
                    success=False,
                    latency_ms=_timed_ms(started_at),
                    error=exc.__class__.__name__,
                )
            )

    fallback_started_at = time.perf_counter()
    fallback_provider = AudibleFallbackToneProvider(active_settings)
    fallback_pcm = await fallback_provider.synthesize(clean_text, language)
    fallback_audio = pcm16_to_mulaw(fallback_pcm or b"")
    attempts.append(
        TTSAttempt(
            provider=fallback_provider.name,
            configured=True,
            success=bool(fallback_audio),
            latency_ms=_timed_ms(fallback_started_at),
            error=None if fallback_audio else "empty_audio",
        )
    )
    return TTSResult(
        audio=fallback_audio or None,
        provider=fallback_provider.name if fallback_audio else None,
        latency_ms=_timed_ms(total_started_at),
        attempts=attempts,
        fallback_tone=bool(fallback_audio),
    )


async def synthesize_speech(text: str, language: str = "english") -> bytes | None:
    """Compatibility wrapper returning only mu-law audio bytes."""

    result = await synthesize_speech_with_fallback(text, language)
    return result.audio

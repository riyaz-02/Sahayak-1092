from __future__ import annotations

from dataclasses import dataclass

import pytest

from backend.config import Settings
from backend.api.health import build_voice_provider_status
from backend.voice.audio_codec import pcm16_to_mulaw
from backend.voice.stt import ordered_stt_providers, transcribe_audio_with_fallback
from backend.voice.tts import (
    PhraseAudioCache,
    ordered_tts_providers,
    synthesize_speech_with_fallback,
)


@dataclass
class FakeSTTProvider:
    name: str
    text: str | None = None
    configured: bool = True
    calls: int = 0

    def is_configured(self) -> bool:
        return self.configured

    async def transcribe(self, audio_bytes: bytes, language: str) -> str | None:
        self.calls += 1
        return self.text


@dataclass
class FakeTTSProvider:
    name: str
    pcm_audio: bytes | None = None
    configured: bool = True
    calls: int = 0

    def is_configured(self) -> bool:
        return self.configured

    async def synthesize(self, text: str, language: str) -> bytes | None:
        self.calls += 1
        return self.pcm_audio


@pytest.mark.asyncio
async def test_stt_provider_fallback_order_skips_empty_transcripts() -> None:
    first = FakeSTTProvider("first", text=None)
    second = FakeSTTProvider("second", text="caller needs help")

    result = await transcribe_audio_with_fallback(
        b"\x00\x01" * 160,
        "english",
        settings=Settings(voice_provider_timeout_sec=1),
        providers=[first, second],
    )

    assert result.text == "caller needs help"
    assert result.provider == "second"
    assert first.calls == 1
    assert second.calls == 1
    assert [attempt.provider for attempt in result.attempts] == ["first", "second"]
    assert result.attempts[0].error == "empty_transcript"


@pytest.mark.asyncio
async def test_stt_provider_fallback_order_skips_unconfigured_provider() -> None:
    first = FakeSTTProvider("first", text="should not run", configured=False)
    second = FakeSTTProvider("second", text="namaste")

    result = await transcribe_audio_with_fallback(
        b"\x00\x01" * 160,
        "hindi",
        settings=Settings(voice_provider_timeout_sec=1),
        providers=[first, second],
    )

    assert result.text == "namaste"
    assert first.calls == 0
    assert second.calls == 1
    assert result.attempts[0].error == "not_configured"


@pytest.mark.asyncio
async def test_tts_common_phrase_cache_avoids_second_provider_call() -> None:
    pcm_audio = b"\x10\x00" * 320
    provider = FakeTTSProvider("primary", pcm_audio=pcm_audio)
    cache = PhraseAudioCache(common_phrases={"english": {"Please say yes or no."}})
    settings = Settings(tts_phrase_cache_enabled=True, voice_provider_timeout_sec=1)

    first = await synthesize_speech_with_fallback(
        "Please say yes or no.",
        "english",
        settings=settings,
        providers=[provider],
        cache=cache,
    )
    second = await synthesize_speech_with_fallback(
        "Please say yes or no.",
        "english",
        settings=settings,
        providers=[provider],
        cache=cache,
    )

    assert first.provider == "primary"
    assert first.audio == pcm16_to_mulaw(pcm_audio)
    assert second.provider == "phrase_cache"
    assert second.from_cache is True
    assert second.audio == first.audio
    assert provider.calls == 1


@pytest.mark.asyncio
async def test_tts_no_silence_fallback_returns_audible_audio_when_providers_fail() -> None:
    result = await synthesize_speech_with_fallback(
        "Provider failure should still produce audible feedback.",
        "english",
        settings=Settings(
            tts_phrase_cache_enabled=False,
            voice_provider_timeout_sec=1,
        ),
        providers=[FakeTTSProvider("failed", pcm_audio=None)],
    )

    assert result.provider == "fallback_tone"
    assert result.fallback_tone is True
    assert result.audio is not None
    assert len(result.audio) > 0
    assert result.attempts[-1].provider == "fallback_tone"


def test_configured_provider_order_is_used_for_voice_cascades() -> None:
    settings = Settings(
        stt_provider_order=("openai_whisper", "deepgram"),
        tts_provider_order=("edge", "google"),
    )

    assert [provider.name for provider in ordered_stt_providers(settings)] == [
        "openai_whisper",
        "deepgram",
    ]
    assert [provider.name for provider in ordered_tts_providers(settings)] == [
        "edge",
        "google",
    ]


def test_sarvam_can_be_selected_as_primary_voice_provider() -> None:
    settings = Settings(
        sarvam_api_key="sarvam_test_key",
        stt_provider_order=("sarvam", "deepgram"),
        tts_provider_order=("sarvam", "edge"),
    )

    assert [provider.name for provider in ordered_stt_providers(settings)] == [
        "sarvam",
        "deepgram",
    ]
    assert [provider.name for provider in ordered_tts_providers(settings)] == [
        "sarvam",
        "edge",
    ]
    status = build_voice_provider_status(settings)
    assert status["stt"] == {"provider": "sarvam", "configured": True}
    assert status["tts"] == {"provider": "sarvam", "configured": True}

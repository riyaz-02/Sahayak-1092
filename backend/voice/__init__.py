"""Voice layer for audio codecs, VAD, STT, TTS, and stream handling."""

from backend.voice.audio_codec import create_wav_header, mulaw_to_pcm16, pcm16_to_mulaw
from backend.voice.stt import transcribe_audio_with_fallback
from backend.voice.tts import synthesize_speech_with_fallback, warm_common_phrase_cache

__all__ = [
    "create_wav_header",
    "mulaw_to_pcm16",
    "pcm16_to_mulaw",
    "synthesize_speech_with_fallback",
    "transcribe_audio_with_fallback",
    "warm_common_phrase_cache",
]

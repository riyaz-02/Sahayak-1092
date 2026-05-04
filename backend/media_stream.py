"""
Sahayak 1092 – Media Stream WebSocket Handler
===============================================
Handles the real-time audio pipeline:
  Twilio Media Stream (mulaw/8kHz) → STT → Decision Engine → TTS → back to caller

Supports:
  • Bhashini STT/TTS (primary – Indian languages)
  • Deepgram STT (fallback – streaming)
  • OpenAI Whisper STT (fallback – batch)
  • OpenAI TTS (fallback)
"""

import os
import json
import base64
import asyncio
import uuid
import struct
from typing import Optional

import httpx
from fastapi import WebSocket, WebSocketDisconnect
from dotenv import load_dotenv

from backend.decision_engine import (
    process_caller_input,
    get_or_create_call,
    get_greeting,
    remove_call,
    active_calls,
    CallOutcome,
)
from backend import supabase_client as db

load_dotenv()

# ── Config ──────────────────────────────────────
BHASHINI_API_KEY = os.getenv("BHASHINI_API_KEY", "")
BHASHINI_USER_ID = os.getenv("BHASHINI_USER_ID", "")
BHASHINI_PIPELINE_URL = os.getenv("BHASHINI_PIPELINE_URL", "https://dhruva-api.bhashini.gov.in/services/inference")
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")


def is_valid_key(key: str) -> bool:
    """Skip empty or placeholder keys like 'your_xxx_api_key'."""
    return bool(key) and not key.startswith("your_")


# Audio buffer config
SILENCE_THRESHOLD = 0.02
SILENCE_DURATION_MS = 1500   # 1.5s of silence → end of utterance
BUFFER_MAX_DURATION_MS = 15000  # 15s max utterance

# Twilio mulaw encoding
MULAW_SAMPLE_RATE = 8000
MULAW_CHANNELS = 1


# ──────────────────────────────────────────────
# BHASHINI STT (Speech-to-Text)
# ──────────────────────────────────────────────

async def bhashini_stt(audio_base64: str, language: str = "kn") -> Optional[str]:
    """Transcribe audio using Bhashini/Dhruva API."""
    lang_map = {
        "kannada": "kn", "hindi": "hi", "english": "en",
        "telugu": "te", "tamil": "ta", "urdu": "ur",
        "kn": "kn", "hi": "hi", "en": "en",
    }
    src_lang = lang_map.get(language.lower(), "kn")

    payload = {
        "pipelineTasks": [
            {
                "taskType": "asr",
                "config": {
                    "language": {"sourceLanguage": src_lang},
                    "audioFormat": "wav",
                    "samplingRate": 8000,
                }
            }
        ],
        "inputData": {
            "audio": [{"audioContent": audio_base64}]
        }
    }

    headers = {
        "Authorization": BHASHINI_API_KEY,
        "Content-Type": "application/json",
    }
    if BHASHINI_USER_ID:
        headers["userID"] = BHASHINI_USER_ID

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(BHASHINI_PIPELINE_URL, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            # Extract transcription from Bhashini response
            output = data.get("pipelineResponse", [{}])
            if output:
                texts = output[0].get("output", [{}])
                if texts:
                    return texts[0].get("source", "")
    except Exception as e:
        print(f"⚠️  Bhashini STT error: {e}")
    return None


# ──────────────────────────────────────────────
# BHASHINI TTS (Text-to-Speech)
# ──────────────────────────────────────────────

async def bhashini_tts(text: str, language: str = "kn") -> Optional[str]:
    """Convert text to speech using Bhashini, returns base64 audio."""
    lang_map = {
        "kannada": "kn", "hindi": "hi", "english": "en",
        "telugu": "te", "tamil": "ta", "urdu": "ur",
        "kn": "kn", "hi": "hi", "en": "en",
    }
    src_lang = lang_map.get(language.lower(), "kn")

    payload = {
        "pipelineTasks": [
            {
                "taskType": "tts",
                "config": {
                    "language": {"sourceLanguage": src_lang},
                    "gender": "female",
                    "samplingRate": 8000,
                }
            }
        ],
        "inputData": {
            "input": [{"source": text}]
        }
    }

    headers = {
        "Authorization": BHASHINI_API_KEY,
        "Content-Type": "application/json",
    }
    if BHASHINI_USER_ID:
        headers["userID"] = BHASHINI_USER_ID

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(BHASHINI_PIPELINE_URL, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            output = data.get("pipelineResponse", [{}])
            if output:
                audios = output[0].get("audio", [{}])
                if audios:
                    return audios[0].get("audioContent", "")
    except Exception as e:
        print(f"⚠️  Bhashini TTS error: {e}")
    return None


# ──────────────────────────────────────────────
# DEEPGRAM STT (Fallback)
# ──────────────────────────────────────────────

async def deepgram_stt(audio_bytes: bytes, language: str = "hi") -> Optional[str]:
    """Transcribe audio using Deepgram Nova-2."""
    lang_map = {
        "kannada": "kn", "hindi": "hi", "english": "en",
        "kn": "kn", "hi": "hi", "en": "en",
    }
    lang_code = lang_map.get(language.lower(), "hi")

    headers = {
        "Authorization": f"Token {DEEPGRAM_API_KEY}",
        "Content-Type": "audio/wav",
    }

    url = f"https://api.deepgram.com/v1/listen?model=nova-2&language={lang_code}&smart_format=true"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, content=audio_bytes, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            transcript = data["results"]["channels"][0]["alternatives"][0]["transcript"]
            return transcript if transcript else None
    except Exception as e:
        print(f"⚠️  Deepgram STT error: {e}")
    return None


# ──────────────────────────────────────────────
# OPENAI WHISPER STT (Fallback)
# ──────────────────────────────────────────────

async def whisper_stt(audio_bytes: bytes) -> Optional[str]:
    """Transcribe audio using OpenAI Whisper."""
    from openai import AsyncOpenAI
    try:
        client = AsyncOpenAI(api_key=OPENAI_API_KEY)
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(audio_bytes)
            f.flush()
            with open(f.name, "rb") as audio_file:
                resp = await client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    language=None,  # auto-detect
                )
                return resp.text if resp.text else None
    except Exception as e:
        print(f"⚠️  Whisper STT error: {e}")
    return None


# ──────────────────────────────────────────────
# OPENAI TTS (Fallback)
# ──────────────────────────────────────────────

async def openai_tts(text: str) -> Optional[bytes]:
    """Convert text to speech using OpenAI TTS."""
    from openai import AsyncOpenAI
    try:
        client = AsyncOpenAI(api_key=OPENAI_API_KEY)
        resp = await client.audio.speech.create(
            model="tts-1",
            voice="nova",
            input=text,
            response_format="pcm",
            speed=0.95,
        )
        return resp.content
    except Exception as e:
        print(f"⚠️  OpenAI TTS error: {e}")
    return None


# ──────────────────────────────────────────────
# GOOGLE CLOUD STT (Speech-to-Text REST — paid Cloud API)
# ──────────────────────────────────────────────

async def gemini_stt(audio_bytes: bytes, language: str = "english") -> Optional[str]:
    """
    Google Cloud Speech-to-Text REST API (v1).
    Uses the same API key as Gemini — hits the proper paid Cloud quota.
    """
    if not is_valid_key(GEMINI_API_KEY):
        return None
    if not audio_bytes:
        return None
    lang_codes = {
        "kannada": "kn-IN", "hindi": "hi-IN", "english": "en-IN",
        "telugu": "te-IN", "tamil": "ta-IN", "urdu": "ur-IN",
    }
    lang_code = lang_codes.get(language.lower(), "en-IN")
    audio_b64 = base64.b64encode(audio_bytes).decode()
    payload = {
        "config": {
            "encoding": "LINEAR16",
            "sampleRateHertz": 8000,
            "languageCode": lang_code,
            # Minimal config — no enhanced/phone_call model (needs special pricing)
        },
        "audio": {"content": audio_b64},
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"https://speech.googleapis.com/v1/speech:recognize?key={GEMINI_API_KEY}",
                json=payload,
            )
            if not resp.is_success:
                print(f"⚠️  Google Cloud STT {resp.status_code}: {resp.text[:400]}")
                return None
            data = resp.json()
            results = data.get("results", [])
            if not results:
                print(f"🔇 STT: No speech detected (empty result) — {len(audio_bytes)} bytes audio")
                return None
            transcript = results[0]["alternatives"][0].get("transcript", "").strip()
            if transcript:
                print(f"✅ STT transcript: {transcript[:80]}")
            return transcript if transcript else None
    except Exception as e:
        print(f"⚠️  Google Cloud STT error: {e}")
    return None


# ──────────────────────────────────────────────
# Google Cloud TTS (REST — no ffmpeg, uses same API key)
# ──────────────────────────────────────────────

async def google_cloud_tts(text: str, language: str = "english") -> Optional[bytes]:
    """
    Google Cloud Text-to-Speech REST API.
    Returns LINEAR16 PCM at 8kHz — no ffmpeg needed.
    Uses the same Gemini/Google API key.
    """
    if not GEMINI_API_KEY:
        return None
    lang_codes = {
        "kannada": ("kn-IN", "kn-IN-Wavenet-A"),
        "hindi":   ("hi-IN", "hi-IN-Wavenet-A"),
        "english": ("en-IN", "en-IN-Wavenet-A"),
        "telugu":  ("te-IN", "te-IN-Standard-A"),
        "tamil":   ("ta-IN", "ta-IN-Wavenet-A"),
        "urdu":    ("ur-IN", "ur-IN-Wavenet-A"),
    }
    lang_code, voice_name = lang_codes.get(language.lower(), ("en-IN", "en-IN-Wavenet-A"))
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
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"https://texttospeech.googleapis.com/v1/text:synthesize?key={GEMINI_API_KEY}",
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            raw = base64.b64decode(data["audioContent"])
            # Google TTS LINEAR16 returns a WAV file — parse properly with wave module
            import wave, io as _io
            try:
                with wave.open(_io.BytesIO(raw)) as wf:
                    pcm_bytes = wf.readframes(wf.getnframes())
            except Exception:
                # Fallback: strip 44-byte WAV header manually
                pcm_bytes = raw[44:] if raw[:4] == b"RIFF" else raw
            print(f"🔊 Google Cloud TTS: {len(pcm_bytes)} bytes PCM ({len(pcm_bytes)/8000:.1f}s)")
            return pcm_bytes
    except Exception as e:
        print(f"⚠️  Google Cloud TTS error: {e}")
    return None


# ──────────────────────────────────────────────
# Edge TTS (Microsoft — free, no key, Indian languages)
# ──────────────────────────────────────────────

async def edge_tts_synth(text: str, language: str = "english") -> Optional[bytes]:
    """
    Microsoft Edge TTS — completely free, no API key.
    Requests raw-16khz-16bit-mono-pcm directly, then downsamples to 8kHz.
    Supports Kannada, Hindi, Telugu, Tamil, English (Indian).
    """
    voices = {
        "kannada": "kn-IN-GaganNeural",
        "hindi":   "hi-IN-SwaraNeural",
        "english": "en-IN-NeerjaNeural",
        "telugu":  "te-IN-ShrutiNeural",
        "tamil":   "ta-IN-PallaviNeural",
        "urdu":    "ur-PK-AsadNeural",
    }
    voice = voices.get(language.lower(), "en-IN-NeerjaNeural")
    try:
        import edge_tts
        import audioop
        import io

        communicate = edge_tts.Communicate(
            text, voice,
            rate="-5%",
            # Request raw PCM to avoid ffmpeg dependency
        )
        # Collect all audio chunks
        pcm_16k = b""
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                pcm_16k += chunk["data"]

        if not pcm_16k:
            return None

        # edge-tts default output is MP3 — strip and resample
        # Try WAV header detection first
        if pcm_16k[:4] == b"RIFF":
            # WAV — strip 44-byte header, then resample 16kHz→8kHz
            raw_16k = pcm_16k[44:]
            raw_8k, _ = audioop.ratecv(raw_16k, 2, 1, 16000, 8000, None)
            print(f"🔊 Edge TTS (WAV→8kHz): {len(raw_8k)} bytes PCM")
            return raw_8k
        else:
            # MP3 — decode with pydub if available, else skip
            try:
                from pydub import AudioSegment
                audio = AudioSegment.from_mp3(io.BytesIO(pcm_16k))
                audio = audio.set_frame_rate(8000).set_channels(1).set_sample_width(2)
                print(f"🔊 Edge TTS (MP3→8kHz): {len(audio.raw_data)} bytes PCM")
                return audio.raw_data
            except Exception:
                print("⚠️  Edge TTS: MP3 decode needs ffmpeg — skipping")
                return None
    except ImportError:
        print("⚠️  edge-tts not installed: pip install edge-tts")
    except Exception as e:
        print(f"⚠️  Edge TTS error: {e}")
    return None


# ──────────────────────────────────────────────
# AUDIO CONVERSION HELPERS
# ──────────────────────────────────────────────

def mulaw_to_pcm16(mulaw_bytes: bytes) -> bytes:
    """Convert mu-law encoded bytes to 16-bit PCM."""
    MULAW_BIAS = 33

    pcm_samples = []
    for byte in mulaw_bytes:
        mu = ~byte & 0xFF
        sign = (mu & 0x80)
        exponent = (mu >> 4) & 0x07
        mantissa = mu & 0x0F
        # FIX: wrap exponent in parens to avoid negative shift (precedence bug)
        sample = ((mantissa << 3) + MULAW_BIAS) << exponent
        sample -= MULAW_BIAS
        if sign != 0:
            sample = -sample
        pcm_samples.append(max(-32768, min(32767, sample)))

    return struct.pack(f'<{len(pcm_samples)}h', *pcm_samples)


def pcm16_to_mulaw(pcm_bytes: bytes) -> bytes:
    """Convert 16-bit PCM to mu-law encoding for Twilio."""
    MULAW_MAX = 0x1FFF
    MULAW_BIAS = 33

    samples = struct.unpack(f'<{len(pcm_bytes)//2}h', pcm_bytes)
    mulaw_bytes = bytearray()

    for sample in samples:
        sign = 0x80 if sample < 0 else 0
        sample = min(abs(sample), MULAW_MAX)
        sample += MULAW_BIAS

        exponent = 7
        for exp in range(7, -1, -1):
            if sample >= (1 << (exp + 3)):
                exponent = exp
                break

        mantissa = (sample >> (exponent + 3)) & 0x0F
        mulaw_byte = ~(sign | (exponent << 4) | mantissa) & 0xFF
        mulaw_bytes.append(mulaw_byte)

    return bytes(mulaw_bytes)


def create_wav_header(pcm_data: bytes, sample_rate: int = 8000, channels: int = 1, bits: int = 16) -> bytes:
    """Create a WAV file header for PCM data."""
    data_size = len(pcm_data)
    header = struct.pack(
        '<4sI4s4sIHHIIHH4sI',
        b'RIFF',
        data_size + 36,
        b'WAVE',
        b'fmt ',
        16,                          # chunk size
        1,                           # PCM format
        channels,
        sample_rate,
        sample_rate * channels * bits // 8,  # byte rate
        channels * bits // 8,        # block align
        bits,
        b'data',
        data_size,
    )
    return header


# ──────────────────────────────────────────────
# SPEECH-TO-TEXT PIPELINE (with fallbacks)
# ──────────────────────────────────────────────

async def transcribe_audio(audio_bytes: bytes, language: str = "english") -> Optional[str]:
    """
    Multi-provider STT with cascading fallback:
    1. Bhashini (best for Indian languages, if key is valid)
    2. Deepgram Nova-2 (if key is valid)
    3. Google Cloud Speech-to-Text REST (paid Cloud API, uses Gemini key)
    4. OpenAI Whisper (if key is valid sk- key)
    Note: audio_bytes is raw mu-law PCM from Twilio.
    """
    # WAV-wrapped audio for providers that need it
    wav_data = create_wav_header(audio_bytes) + audio_bytes
    audio_b64 = base64.b64encode(wav_data).decode("utf-8")

    if is_valid_key(BHASHINI_API_KEY):
        text = await bhashini_stt(audio_b64, language)
        if text and text.strip():
            print(f"🎯 Bhashini STT: {text[:60]}")
            return text.strip()

    if is_valid_key(DEEPGRAM_API_KEY):
        text = await deepgram_stt(wav_data, language)
        if text and text.strip():
            print(f"🎯 Deepgram STT: {text[:60]}")
            return text.strip()

    if is_valid_key(GEMINI_API_KEY):
        # Pass raw PCM (not WAV) — Google Cloud STT LINEAR16 needs raw bytes, no header
        text = await gemini_stt(audio_bytes, language)
        if text and text.strip():
            print(f"🎯 Google Cloud STT: {text[:60]}")
            return text.strip()

    if is_valid_key(OPENAI_API_KEY) and OPENAI_API_KEY.startswith("sk-"):
        text = await whisper_stt(wav_data)
        if text and text.strip():
            print(f"🎯 Whisper STT: {text[:60]}")
            return text.strip()

    print("❌ All STT providers failed")
    return None


# ──────────────────────────────────────────────
# TEXT-TO-SPEECH PIPELINE (with fallbacks)
# ──────────────────────────────────────────────

async def synthesize_speech(text: str, language: str = "english") -> Optional[bytes]:
    """
    Multi-provider TTS with fallback:
    1. Bhashini (natural Indian language voice, if key is valid)
    2. Google Cloud TTS REST (same API key, no ffmpeg, LINEAR16)
    3. Edge TTS (Microsoft — free, no key, Indian voices)
    4. OpenAI TTS (only if real sk- key)
    Returns mu-law encoded bytes ready for Twilio.
    """
    if is_valid_key(BHASHINI_API_KEY):
        audio_b64 = await bhashini_tts(text, language)
        if audio_b64:
            audio_bytes = base64.b64decode(audio_b64)
            mulaw = pcm16_to_mulaw(audio_bytes)
            print(f"🔊 Bhashini TTS: {len(mulaw)} bytes")
            return mulaw

    # Google Cloud TTS (uses Gemini API key, no ffmpeg needed)
    if is_valid_key(GEMINI_API_KEY):
        pcm_bytes = await google_cloud_tts(text, language)
        if pcm_bytes:
            mulaw = pcm16_to_mulaw(pcm_bytes)
            print(f"🔊 Google Cloud TTS→mulaw: {len(mulaw)} bytes")
            return mulaw

    # Edge TTS — free, no key, high-quality Indian neural voices
    pcm_bytes = await edge_tts_synth(text, language)
    if pcm_bytes:
        mulaw = pcm16_to_mulaw(pcm_bytes)
        print(f"🔊 Edge TTS→mulaw: {len(mulaw)} bytes")
        return mulaw

    # OpenAI TTS — only if key is a real OpenAI key (sk-...)
    if OPENAI_API_KEY and OPENAI_API_KEY.startswith("sk-"):
        pcm_bytes = await openai_tts(text)
        if pcm_bytes:
            mulaw = pcm16_to_mulaw(pcm_bytes)
            print(f"🔊 OpenAI TTS: {len(mulaw)} bytes")
            return mulaw

    print("❌ All TTS providers failed")
    return None


# ──────────────────────────────────────────────
# TWILIO MEDIA STREAM WEBSOCKET HANDLER
# ──────────────────────────────────────────────

class MediaStreamHandler:
    """Handles a single Twilio Media Stream WebSocket connection."""

    def __init__(self, websocket: WebSocket):
        self.ws = websocket
        self.stream_sid: str = ""
        self.call_sid: str = ""
        self.caller_number: str = ""
        self.audio_buffer: bytearray = bytearray()
        self.silence_counter: int = 0
        self.is_speaking: bool = False
        self.processing: bool = False
        self.greeting_sent: bool = False
        self.sequence_number: int = 0

    async def handle(self):
        """Main WebSocket handler loop."""
        try:
            await self.ws.accept()
            print("🔌 WebSocket connected")

            async for message in self.ws.iter_text():
                try:
                    data = json.loads(message)
                    event = data.get("event")

                    if event == "connected":
                        print("📞 Twilio Media Stream connected")

                    elif event == "start":
                        self.stream_sid = data["start"]["streamSid"]
                        self.call_sid = data["start"]["callSid"]
                        custom = data["start"].get("customParameters", {})
                        self.caller_number = custom.get("callerNumber", "unknown")
                        print(f"🎙️ Stream started: {self.stream_sid} (Call: {self.call_sid})")

                        # Create call log in DB (non-fatal if Supabase not configured)
                        try:
                            db.create_call_log(self.call_sid, self.caller_number)
                        except Exception as db_err:
                            print(f"⚠️  DB skipped (not configured): {db_err}")

                        # Initialize call state
                        call_state = get_or_create_call(self.call_sid, self.caller_number)

                        # Send greeting
                        if not self.greeting_sent:
                            await self._send_greeting()
                            self.greeting_sent = True

                    elif event == "media":
                        payload = data["media"]["payload"]
                        audio_chunk = base64.b64decode(payload)
                        await self._handle_audio_chunk(audio_chunk)

                    elif event == "dtmf":
                        digit = data["dtmf"]["digit"]
                        await self._handle_dtmf(digit)

                    elif event == "stop":
                        print(f"🔇 Stream stopped: {self.stream_sid}")
                        remove_call(self.call_sid)
                        break

                except json.JSONDecodeError:
                    continue
                except Exception as e:
                    print(f"❌ Message handling error: {e}")

        except WebSocketDisconnect:
            print("🔌 WebSocket disconnected")
            remove_call(self.call_sid)
        except Exception as e:
            print(f"❌ WebSocket error: {e}")
            remove_call(self.call_sid)

    async def _send_greeting(self):
        """Send the initial greeting to the caller."""
        call_state = get_or_create_call(self.call_sid)
        greeting = get_greeting(call_state.language)
        call_state.transcript.append({"role": "sahayak", "text": greeting})

        audio_bytes = await synthesize_speech(greeting, call_state.language)
        if audio_bytes:
            await self._send_audio(audio_bytes)
        else:
            print("⚠️  Greeting TTS failed, caller will hear silence")

    async def _handle_audio_chunk(self, audio_chunk: bytes):
        """Process incoming audio chunks, detect end of utterance via silence."""
        if self.processing or not audio_chunk:
            return  # Don't buffer while processing a response

        # ── Correct VAD for mu-law audio ──────────────────────────────────
        # mu-law silence = 0xFF or 0x7F, NOT 0x80. Converting to PCM first
        # gives the true signal amplitude for accurate VAD.
        pcm_chunk = mulaw_to_pcm16(audio_chunk)
        samples = struct.unpack(f'<{len(pcm_chunk)//2}h', pcm_chunk)
        rms = (sum(s * s for s in samples) / len(samples)) ** 0.5
        normalised_energy = rms / 32768.0   # 0.0 = silence, 1.0 = max

        if normalised_energy > SILENCE_THRESHOLD:
            self.is_speaking = True
            self.silence_counter = 0
            self.audio_buffer.extend(audio_chunk)
        else:
            self.silence_counter += len(audio_chunk) * 1000 // MULAW_SAMPLE_RATE  # ms

            if self.is_speaking:
                self.audio_buffer.extend(audio_chunk)

                # End of utterance detected
                if self.silence_counter >= SILENCE_DURATION_MS:
                    if len(self.audio_buffer) > MULAW_SAMPLE_RATE * 0.5:  # min 0.5s
                        await self._process_utterance()
                    self.audio_buffer = bytearray()
                    self.is_speaking = False
                    self.silence_counter = 0

        # Prevent excessively long buffers
        max_bytes = MULAW_SAMPLE_RATE * BUFFER_MAX_DURATION_MS // 1000
        if len(self.audio_buffer) > max_bytes:
            await self._process_utterance()
            self.audio_buffer = bytearray()
            self.is_speaking = False

    async def _process_utterance(self):
        """Process a complete utterance: STT → Decision Engine → TTS → Send."""
        if self.processing or len(self.audio_buffer) == 0:
            return

        self.processing = True
        try:
            # Convert mulaw buffer to PCM for STT
            pcm_data = mulaw_to_pcm16(bytes(self.audio_buffer))

            call_state = get_or_create_call(self.call_sid)

            # ── STT ──
            text = await transcribe_audio(pcm_data, call_state.language)
            if not text:
                self.processing = False
                return

            print(f"👤 Caller [{self.call_sid[-6:]}]: {text}")

            # ── Decision Engine ──
            result = await process_caller_input(
                call_sid=self.call_sid,
                text=text,
                caller_number=self.caller_number,
            )

            response_text = result["response_text"]
            action = result["action"]
            print(f"🤖 Sahayak [{self.call_sid[-6:]}]: {response_text[:80]}... (action: {action})")

            # ── TTS ──
            audio_bytes = await synthesize_speech(response_text, call_state.language)
            if audio_bytes:
                await self._send_audio(audio_bytes)

            # ── Handle actions ──
            if action == "handover":
                # In production: initiate Twilio conference/warm transfer
                print(f"📞 Handing over to agent: {result.get('agent', {}).get('name', '?')}")

            elif action == "queue":
                # Start IVR timer
                asyncio.create_task(self._queue_timeout())

            elif action == "resolve":
                print(f"✅ Call resolved by AI: {self.call_sid[-6:]}")

        except Exception as e:
            print(f"❌ Utterance processing error: {e}")
        finally:
            self.processing = False

    async def _handle_dtmf(self, digit: str):
        """Handle DTMF tones for IVR during queue."""
        call_state = active_calls.get(self.call_sid)
        if not call_state or call_state.current_phase != "queued":
            return

        print(f"📱 DTMF received: {digit}")

        redirects = {
            "1": "Police",
            "2": "Ambulance (108)",
            "3": "Fire Services (101)",
        }

        if digit in redirects:
            service = redirects[digit]
            msg = f"Redirecting you to {service} now. Please hold."
            audio = await synthesize_speech(msg, call_state.language)
            if audio:
                await self._send_audio(audio)
            call_state.outcome = CallOutcome.HANDED_OVER
            db.update_call_log(
                call_sid=self.call_sid,
                outcome="ivr_redirect",
                ai_summary=f"IVR redirect to {service}",
            )
            print(f"📞 IVR redirect to {service}")

    async def _queue_timeout(self):
        """After 2 minutes in queue with no response → auto-transfer as High-Help Alert."""
        await asyncio.sleep(120)  # 2 minutes
        call_state = active_calls.get(self.call_sid)
        if call_state and call_state.current_phase == "queued":
            print(f"🚨 HIGH-HELP ALERT: Auto-transferring {self.call_sid[-6:]} to Police")
            call_state.outcome = CallOutcome.HANDED_OVER
            msg = "We are transferring you to the nearest police station now. Help is on the way."
            audio = await synthesize_speech(msg, call_state.language)
            if audio:
                await self._send_audio(audio)
            db.update_call_log(
                call_sid=self.call_sid,
                outcome="high_help_alert",
                ai_summary="Auto-transferred: 2min queue timeout → High-Help Alert",
            )

    async def _send_audio(self, mulaw_audio: bytes):
        """Send mu-law audio bytes back to Twilio via the WebSocket."""
        # Twilio expects base64-encoded mulaw in 160-byte chunks (20ms)
        chunk_size = 160
        for i in range(0, len(mulaw_audio), chunk_size):
            chunk = mulaw_audio[i:i + chunk_size]
            payload = base64.b64encode(chunk).decode("utf-8")
            message = {
                "event": "media",
                "streamSid": self.stream_sid,
                "media": {
                    "payload": payload,
                },
            }
            try:
                await self.ws.send_json(message)
            except Exception:
                break
            # Pace to exactly 20ms per chunk (Twilio's native frame rate = 160 bytes @ 8kHz)
            await asyncio.sleep(0.020)

    async def _send_mark(self, name: str):
        """Send a mark event to track audio playback position."""
        message = {
            "event": "mark",
            "streamSid": self.stream_sid,
            "mark": {"name": name},
        }
        await self.ws.send_json(message)


# ──────────────────────────────────────────────
# WEBSOCKET ENDPOINT (used by main.py)
# ──────────────────────────────────────────────

async def handle_media_stream(websocket: WebSocket):
    """Entry point for Twilio Media Stream WebSocket."""
    handler = MediaStreamHandler(websocket)
    await handler.handle()

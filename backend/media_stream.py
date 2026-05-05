"""Sahayak 1092 Twilio Media Stream handler.

Pipeline:
Twilio mu-law audio -> VAD -> STT provider cascade -> decision engine ->
TTS provider cascade -> Twilio mu-law audio.
"""

from __future__ import annotations

import asyncio
import base64
import json
import time

from dotenv import load_dotenv
from fastapi import WebSocket, WebSocketDisconnect

from backend import supabase_client as db
from backend.config import get_settings
from backend.decision_engine import (
    CallOutcome,
    active_calls,
    get_greeting,
    get_or_create_call,
    process_caller_input,
    remove_call,
)
from backend.persistence.repository import get_call_repository
from backend.routing.queue_manager import DTMF_SERVICE_MAP, get_queue_manager
from backend.security import json_log
from backend.voice.audio_codec import (
    MULAW_SAMPLE_RATE,
    create_wav_header as _create_wav_header,
    mulaw_to_pcm16 as _mulaw_to_pcm16,
    pcm16_to_mulaw as _pcm16_to_mulaw,
)
from backend.voice.stt import STTResult, transcribe_audio_with_fallback
from backend.voice.tts import TTSResult, synthesize_speech_with_fallback
from backend.voice.vad import normalized_energy_from_mulaw


load_dotenv()
settings = get_settings()
call_repository = get_call_repository()
queue_manager = get_queue_manager()

SILENCE_THRESHOLD = settings.vad_silence_threshold
SILENCE_DURATION_MS = settings.vad_silence_duration_ms
BUFFER_MAX_DURATION_MS = settings.vad_buffer_max_duration_ms


def mulaw_to_pcm16(mulaw_bytes: bytes) -> bytes:
    """Compatibility wrapper for the voice audio codec module."""

    return _mulaw_to_pcm16(mulaw_bytes)


def pcm16_to_mulaw(pcm_bytes: bytes) -> bytes:
    """Compatibility wrapper for the voice audio codec module."""

    return _pcm16_to_mulaw(pcm_bytes)


def create_wav_header(
    pcm_data: bytes,
    sample_rate: int = MULAW_SAMPLE_RATE,
    channels: int = 1,
    bits: int = 16,
) -> bytes:
    """Compatibility wrapper for the voice audio codec module."""

    return _create_wav_header(pcm_data, sample_rate=sample_rate, channels=channels, bits=bits)


async def transcribe_audio(audio_bytes: bytes, language: str = "english") -> str | None:
    """Compatibility wrapper returning only transcript text."""

    result = await transcribe_audio_with_fallback(audio_bytes, language)
    return result.text


async def synthesize_speech(text: str, language: str = "english") -> bytes | None:
    """Compatibility wrapper returning only Twilio-ready mu-law bytes."""

    result = await synthesize_speech_with_fallback(text, language)
    return result.audio


def _elapsed_ms(started_at: float) -> float:
    return round((time.perf_counter() - started_at) * 1000, 2)


class MediaStreamHandler:
    """Handles one Twilio Media Stream WebSocket connection."""

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

    async def handle(self) -> None:
        """Main WebSocket event loop."""

        try:
            await self.ws.accept()
            json_log("websocket_connected")

            async for message in self.ws.iter_text():
                try:
                    data = json.loads(message)
                    event = data.get("event")

                    if event == "connected":
                        json_log("twilio_media_connected")

                    elif event == "start":
                        await self._handle_start(data)

                    elif event == "media":
                        payload = data["media"]["payload"]
                        await self._handle_audio_chunk(base64.b64decode(payload))

                    elif event == "dtmf":
                        await self._handle_dtmf(data["dtmf"]["digit"])

                    elif event == "stop":
                        json_log("stream_stopped", stream_sid=self.stream_sid, call_sid=self.call_sid)
                        remove_call(self.call_sid)
                        break

                except json.JSONDecodeError:
                    continue
                except Exception as exc:
                    json_log("media_message_error", call_sid=self.call_sid, error=str(exc))

        except WebSocketDisconnect:
            json_log("websocket_disconnected", call_sid=self.call_sid)
            remove_call(self.call_sid)
        except Exception as exc:
            json_log("websocket_error", call_sid=self.call_sid, error=str(exc))
            remove_call(self.call_sid)

    async def _handle_start(self, data: dict) -> None:
        self.stream_sid = data["start"]["streamSid"]
        self.call_sid = data["start"]["callSid"]
        custom = data["start"].get("customParameters", {})
        self.caller_number = custom.get("callerNumber", "unknown")
        json_log("stream_started", stream_sid=self.stream_sid, call_sid=self.call_sid)

        call_state = get_or_create_call(self.call_sid, self.caller_number)
        try:
            call_repository.create_call_state(call_state)
        except Exception as exc:
            json_log("call_state_persistence_skipped", call_sid=self.call_sid, error=str(exc))

        if not self.greeting_sent:
            await self._send_greeting()
            self.greeting_sent = True

    async def _send_greeting(self) -> None:
        """Send the initial Sahayak greeting to the caller."""

        call_state = get_or_create_call(self.call_sid, self.caller_number)
        greeting = get_greeting(call_state.language)
        call_state.transcript.append({"role": "sahayak", "text": greeting})
        call_repository.update_call_state(call_state)
        call_repository.append_call_event(
            call_sid=self.call_sid,
            event_type="greeting_sent",
            payload={"text": greeting},
            call_state=call_state,
        )
        await self._speak(greeting, call_state.language, context="greeting", call_state=call_state)

    async def _handle_audio_chunk(self, audio_chunk: bytes) -> None:
        """Buffer caller audio and trigger utterance processing after silence."""

        if self.processing or not audio_chunk:
            return

        normalised_energy = normalized_energy_from_mulaw(audio_chunk)
        if normalised_energy > SILENCE_THRESHOLD:
            self.is_speaking = True
            self.silence_counter = 0
            self.audio_buffer.extend(audio_chunk)
        else:
            self.silence_counter += len(audio_chunk) * 1000 // MULAW_SAMPLE_RATE
            if self.is_speaking:
                self.audio_buffer.extend(audio_chunk)
                if self.silence_counter >= SILENCE_DURATION_MS:
                    if len(self.audio_buffer) > MULAW_SAMPLE_RATE * 0.5:
                        await self._process_utterance()
                    self.audio_buffer = bytearray()
                    self.is_speaking = False
                    self.silence_counter = 0

        max_bytes = MULAW_SAMPLE_RATE * BUFFER_MAX_DURATION_MS // 1000
        if len(self.audio_buffer) > max_bytes:
            await self._process_utterance()
            self.audio_buffer = bytearray()
            self.is_speaking = False

    async def _process_utterance(self) -> None:
        """Process a complete utterance from audio to spoken response."""

        if self.processing or not self.audio_buffer:
            return

        self.processing = True
        turn_started_at = time.perf_counter()
        stt_result: STTResult | None = None
        tts_result: TTSResult | None = None
        decision_latency_ms: float | None = None
        action: str | None = None

        try:
            call_state = get_or_create_call(self.call_sid, self.caller_number)
            pcm_data = mulaw_to_pcm16(bytes(self.audio_buffer))

            stt_result = await transcribe_audio_with_fallback(pcm_data, call_state.language)
            if not stt_result.text:
                call_repository.append_call_event(
                    call_sid=self.call_sid,
                    event_type="stt_failed",
                    payload={
                        **stt_result.as_event_payload(),
                        "language": call_state.language,
                    },
                    call_state=call_state,
                )
                return

            json_log("caller_transcribed", call_sid=self.call_sid, text=stt_result.text)
            call_repository.append_call_event(
                call_sid=self.call_sid,
                event_type="stt_completed",
                payload={
                    **stt_result.as_event_payload(),
                    "language": call_state.language,
                },
                call_state=call_state,
            )

            decision_started_at = time.perf_counter()
            result = await process_caller_input(
                call_sid=self.call_sid,
                text=stt_result.text,
                caller_number=self.caller_number,
            )
            decision_latency_ms = _elapsed_ms(decision_started_at)

            response_text = result["response_text"]
            action = result["action"]
            updated_state = get_or_create_call(self.call_sid, self.caller_number)
            json_log(
                "sahayak_response",
                call_sid=self.call_sid,
                text=response_text,
                action=action,
            )

            tts_result = await self._speak(
                response_text,
                updated_state.language,
                context=f"response:{action}",
                call_state=updated_state,
            )

            call_repository.append_call_event(
                call_sid=self.call_sid,
                event_type="voice_turn_completed",
                payload={
                    "action": action,
                    "total_latency_ms": _elapsed_ms(turn_started_at),
                    "stt_latency_ms": stt_result.latency_ms,
                    "decision_latency_ms": decision_latency_ms,
                    "tts_latency_ms": tts_result.latency_ms if tts_result else None,
                    "stt_provider": stt_result.provider,
                    "tts_provider": tts_result.provider if tts_result else None,
                    "tts_fallback_tone": tts_result.fallback_tone if tts_result else None,
                },
                call_state=updated_state,
            )

            if action == "handover":
                json_log(
                    "handover_response_ready",
                    call_sid=self.call_sid,
                    agent=result.get("agent", {}).get("name", "?"),
                )
            elif action == "queue":
                asyncio.create_task(self._queue_timeout(queue_manager.queue_timeout_sec()))
            elif action == "resolve":
                json_log("call_resolved_by_ai", call_sid=self.call_sid)

        except Exception as exc:
            json_log("utterance_processing_error", call_sid=self.call_sid, error=str(exc))
        finally:
            self.processing = False

    async def _handle_dtmf(self, digit: str) -> None:
        """Handle DTMF tones for surge IVR during queue state."""

        call_state = active_calls.get(self.call_sid)
        if not call_state or call_state.current_phase != "queued":
            return

        service = DTMF_SERVICE_MAP.get(digit)
        if not service:
            return

        queue_entry = queue_manager.redirect_to_service(self.call_sid, digit)
        queue_manager.apply_to_call_state(call_state, queue_entry)
        msg = f"Redirecting you to {service['service']} now. Please hold."
        await self._speak(msg, call_state.language, context="dtmf_redirect", call_state=call_state)
        call_state.outcome = CallOutcome.HANDED_OVER
        call_repository.append_call_event(
            call_sid=self.call_sid,
            event_type="dtmf_redirect",
            payload={
                "digit": digit,
                "service": service,
                "queue": queue_entry.as_dict() if queue_entry else None,
            },
            call_state=call_state,
        )
        if queue_entry:
            call_repository.append_call_event(
                call_sid=self.call_sid,
                event_type="queue_updated",
                payload=queue_entry.as_dict(),
                call_state=call_state,
            )
        call_repository.update_call_state(call_state)
        db.update_call_log(
            call_sid=self.call_sid,
            outcome="ivr_redirect",
            ai_summary=f"IVR redirect to {service['service']}",
        )
        json_log("ivr_redirect", call_sid=self.call_sid, service=service["service"])

    async def _queue_timeout(self, timeout_sec: int) -> None:
        """After the queue timeout, transfer as a High-Help Alert."""

        await asyncio.sleep(timeout_sec)
        call_state = active_calls.get(self.call_sid)
        if not call_state or call_state.current_phase != "queued":
            return

        json_log("high_help_alert_transfer", call_sid=self.call_sid)
        queue_entry = queue_manager.mark_high_help_alert(self.call_sid)
        queue_manager.apply_to_call_state(call_state, queue_entry)
        call_state.outcome = CallOutcome.HANDED_OVER
        call_repository.append_call_event(
            call_sid=self.call_sid,
            event_type="high_help_alert",
            payload={
                "reason": "queue_timeout",
                "timeout_sec": timeout_sec,
                "queue": queue_entry.as_dict() if queue_entry else None,
            },
            call_state=call_state,
        )
        if queue_entry:
            call_repository.append_call_event(
                call_sid=self.call_sid,
                event_type="queue_updated",
                payload=queue_entry.as_dict(),
                call_state=call_state,
            )
        call_repository.update_call_state(call_state)

        msg = "We are transferring you to the nearest police station now. Help is on the way."
        await self._speak(msg, call_state.language, context="high_help_alert", call_state=call_state)
        db.update_call_log(
            call_sid=self.call_sid,
            outcome="high_help_alert",
            ai_summary="Auto-transferred after queue timeout as High-Help Alert",
        )

    async def _speak(
        self,
        text: str,
        language: str,
        *,
        context: str,
        call_state,
    ) -> TTSResult:
        """Synthesize and send one Sahayak response."""

        result = await synthesize_speech_with_fallback(text, language)
        call_repository.append_call_event(
            call_sid=self.call_sid,
            event_type="tts_completed",
            payload={
                **result.as_event_payload(text=text, language=language),
                "context": context,
            },
            call_state=call_state,
        )
        if result.audio:
            await self._send_audio(result.audio)
        else:
            json_log("tts_failed_without_audio", call_sid=self.call_sid, context=context)
        return result

    async def _send_audio(self, mulaw_audio: bytes) -> None:
        """Send mu-law audio bytes back to Twilio in 20 ms frames."""

        chunk_size = 160
        for i in range(0, len(mulaw_audio), chunk_size):
            chunk = mulaw_audio[i:i + chunk_size]
            payload = base64.b64encode(chunk).decode("utf-8")
            message = {
                "event": "media",
                "streamSid": self.stream_sid,
                "media": {"payload": payload},
            }
            try:
                await self.ws.send_json(message)
            except Exception:
                break
            await asyncio.sleep(0.020)

    async def _send_mark(self, name: str) -> None:
        """Send a Twilio mark event to track audio playback position."""

        message = {
            "event": "mark",
            "streamSid": self.stream_sid,
            "mark": {"name": name},
        }
        await self.ws.send_json(message)


async def handle_media_stream(websocket: WebSocket) -> None:
    """Entrypoint used by the FastAPI Twilio WebSocket route."""

    handler = MediaStreamHandler(websocket)
    await handler.handle()

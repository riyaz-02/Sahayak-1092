"""Warm transfer service for officer handover."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

from backend.config import Settings, get_settings


def _safe_conference_name(call_sid: str) -> str:
    suffix = re.sub(r"[^A-Za-z0-9]", "", call_sid or "local")[-18:] or "local"
    return f"sahayak-1092-{suffix}"


@dataclass(frozen=True)
class TransferRequest:
    """Request to accept a handover and connect caller/officer."""

    call_sid: str
    agent: dict[str, Any]
    handover_context: dict[str, Any]
    notes: str = ""


@dataclass(frozen=True)
class TransferResult:
    """Result of a transfer attempt."""

    success: bool
    mode: str
    status: str
    conference_name: str
    call_sid: str
    agent_id: str
    officer_call_sid: str | None = None
    message: str = ""
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class WarmTransferService:
    """Transfer facade with mock and Twilio implementations."""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()

    def accept_handover(self, request: TransferRequest) -> TransferResult:
        """Accept a handover using mock mode locally or Twilio in production."""

        if self.settings.transfer_mode.lower() != "twilio":
            return self._mock_accept(request)
        return self._twilio_accept(request)

    def _mock_accept(self, request: TransferRequest) -> TransferResult:
        conference_name = _safe_conference_name(request.call_sid)
        return TransferResult(
            success=True,
            mode="mock",
            status="mock_transfer_ready",
            conference_name=conference_name,
            call_sid=request.call_sid,
            agent_id=str(request.agent.get("id") or ""),
            message=(
                "Mock warm transfer accepted. In Twilio mode, caller and officer "
                "would be joined into this conference."
            ),
        )

    def _twilio_accept(self, request: TransferRequest) -> TransferResult:
        if not self.settings.twilio_configured:
            return TransferResult(
                success=False,
                mode="twilio",
                status="not_configured",
                conference_name=_safe_conference_name(request.call_sid),
                call_sid=request.call_sid,
                agent_id=str(request.agent.get("id") or ""),
                error="Twilio credentials or phone number are missing.",
            )

        try:
            from twilio.rest import Client as TwilioClient
            from twilio.twiml.voice_response import Conference, Dial, VoiceResponse

            conference_name = _safe_conference_name(request.call_sid)
            client = TwilioClient(
                self.settings.twilio_account_sid,
                self.settings.twilio_auth_token,
            )

            caller_response = VoiceResponse()
            caller_dial = Dial()
            caller_dial.append(
                Conference(
                    conference_name,
                    start_conference_on_enter=True,
                    end_conference_on_exit=True,
                    beep=False,
                )
            )
            caller_response.append(caller_dial)
            client.calls(request.call_sid).update(twiml=str(caller_response))

            officer_call_sid = None
            officer_phone = str(request.agent.get("phone") or "").strip()
            if officer_phone:
                officer_response = VoiceResponse()
                officer_response.say(
                    "Sahayak 1092 warm handover. Please review the dashboard context.",
                    voice="Polly.Aditi",
                    language="en-IN",
                )
                officer_dial = Dial()
                officer_dial.append(
                    Conference(
                        conference_name,
                        start_conference_on_enter=True,
                        end_conference_on_exit=False,
                        beep=False,
                    )
                )
                officer_response.append(officer_dial)
                officer_call = client.calls.create(
                    to=officer_phone,
                    from_=self.settings.twilio_phone_number,
                    twiml=str(officer_response),
                )
                officer_call_sid = officer_call.sid

            return TransferResult(
                success=True,
                mode="twilio",
                status="conference_initiated",
                conference_name=conference_name,
                call_sid=request.call_sid,
                agent_id=str(request.agent.get("id") or ""),
                officer_call_sid=officer_call_sid,
                message="Twilio conference initiated for caller and selected officer.",
            )
        except Exception as exc:
            return TransferResult(
                success=False,
                mode="twilio",
                status="failed",
                conference_name=_safe_conference_name(request.call_sid),
                call_sid=request.call_sid,
                agent_id=str(request.agent.get("id") or ""),
                error=str(exc),
            )


transfer_service = WarmTransferService()


def get_transfer_service() -> WarmTransferService:
    return transfer_service

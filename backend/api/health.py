"""Health API helpers.

The live `/health` route still lives in `backend.main` during Phase 1. This
module gives later phases a clean place to move health routing.
"""

from __future__ import annotations

from typing import Protocol

from backend.config import Settings, get_settings


class _Provider(Protocol):
    name: str

    def is_configured(self) -> bool:
        """Return true when this provider can be used."""


def _normalise_provider_name(name: str) -> str:
    return name.strip().lower().replace("-", "_")


def _first_configured_provider(
    order: tuple[str, ...],
    providers: dict[str, _Provider],
) -> dict[str, object]:
    for name in order:
        provider = providers.get(_normalise_provider_name(name))
        if not provider:
            continue
        try:
            configured = provider.is_configured()
        except Exception:
            configured = False
        if configured:
            return {"provider": provider.name, "configured": True}
    return {"provider": "none", "configured": False}


def build_voice_provider_status(settings: Settings | None = None) -> dict[str, object]:
    """Return only the currently selected STT/TTS providers for dashboard health."""

    cfg = settings or get_settings()
    from backend.voice.stt import build_stt_providers
    from backend.voice.tts import build_tts_providers

    return {
        "stt": _first_configured_provider(cfg.stt_provider_order, build_stt_providers(cfg)),
        "tts": _first_configured_provider(cfg.tts_provider_order, build_tts_providers(cfg)),
    }


def build_health_payload(
    active_calls: int = 0,
    persistence: dict[str, object] | None = None,
) -> dict[str, object]:
    settings = get_settings()
    payload: dict[str, object] = {
        "status": "healthy",
        "service": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "active_calls": active_calls,
        "voice": build_voice_provider_status(settings),
        "security": {
            "twilio_signature_validation": settings.validate_twilio_signatures,
            "dashboard_auth_required": settings.dashboard_auth_required,
            "rate_limit_enabled": settings.rate_limit_enabled,
            "mask_pii_in_logs": settings.mask_pii_in_logs,
            "data_retention_days": settings.data_retention_days,
        },
    }
    if persistence is not None:
        payload["persistence"] = persistence
    return payload

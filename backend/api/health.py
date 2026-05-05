"""Health API helpers.

The live `/health` route still lives in `backend.main` during Phase 1. This
module gives later phases a clean place to move health routing.
"""

from __future__ import annotations

from backend.config import get_settings


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

"""PII helpers for safe logging and dashboard display."""

from __future__ import annotations


def mask_phone_number(phone: str | None) -> str:
    """Mask a phone number while keeping enough digits for support workflows."""

    if not phone:
        return "unknown"
    normalized = str(phone).strip()
    if len(normalized) <= 4:
        return "*" * len(normalized)
    return f"{'*' * max(len(normalized) - 4, 0)}{normalized[-4:]}"

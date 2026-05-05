"""PII helpers for safe logging and dashboard display."""

from __future__ import annotations

import re
from typing import Any


PHONE_PATTERN = re.compile(r"(?<!\w)(?:\+?\d[\d\s().-]{6,}\d)(?!\w)")
EMAIL_PATTERN = re.compile(r"(?<!\w)[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?!\w)")
SENSITIVE_KEYS = {
    "phone",
    "from",
    "to",
    "caller",
    "caller_number",
    "called",
    "mobile",
    "auth_token",
    "token",
    "api_key",
    "supabase_key",
    "openai_api_key",
}


def mask_phone_number(phone: str | None) -> str:
    """Mask a phone number while keeping enough digits for support workflows."""

    if not phone:
        return "unknown"
    normalized = str(phone).strip()
    if len(normalized) <= 4:
        return "*" * len(normalized)
    return f"{'*' * max(len(normalized) - 4, 0)}{normalized[-4:]}"


def mask_sensitive_text(text: str | None) -> str:
    """Mask common phone/email patterns in free text."""

    if text is None:
        return ""
    value = str(text)
    value = PHONE_PATTERN.sub(lambda match: mask_phone_number(match.group(0)), value)
    value = EMAIL_PATTERN.sub("***@***", value)
    return value


def mask_payload(value: Any) -> Any:
    """Recursively mask PII-ish fields before writing operational logs."""

    if isinstance(value, dict):
        masked: dict[str, Any] = {}
        for key, item in value.items():
            normalized_key = str(key).lower()
            if (
                normalized_key in SENSITIVE_KEYS
                or "phone" in normalized_key
                or normalized_key in {"caller_number", "called_number"}
            ):
                masked[key] = mask_phone_number(str(item)) if item else item
            elif "text" in normalized_key or "summary" in normalized_key:
                masked[key] = mask_sensitive_text(str(item)) if item is not None else item
            else:
                masked[key] = mask_payload(item)
        return masked
    if isinstance(value, list):
        return [mask_payload(item) for item in value]
    if isinstance(value, tuple):
        return [mask_payload(item) for item in value]
    if isinstance(value, str):
        return mask_sensitive_text(value)
    return value

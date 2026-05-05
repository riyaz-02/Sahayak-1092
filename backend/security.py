"""Security helpers for production-facing FastAPI routes."""

from __future__ import annotations

import datetime as dt
import hmac
import json
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from threading import RLock
from typing import Any
from uuid import uuid4

from fastapi import Request
from starlette.datastructures import FormData
from twilio.request_validator import RequestValidator

from backend.config import Settings, get_settings
from backend.persistence.pii import mask_payload


SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
PUBLIC_PATH_PREFIXES = (
    "/",
    "/health",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/twilio",
)


@dataclass(frozen=True)
class AuthDecision:
    allowed: bool
    role: str = "anonymous"
    status_code: int = 401
    detail: str = "Authentication required"


class InMemoryRateLimiter:
    """Small process-local fixed-window limiter for demos and single-worker runs."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str, *, limit: int, window_sec: int = 60) -> tuple[bool, int]:
        if limit <= 0:
            return True, limit
        now = time.monotonic()
        cutoff = now - window_sec
        with self._lock:
            bucket = self._hits[key]
            while bucket and bucket[0] < cutoff:
                bucket.popleft()
            if len(bucket) >= limit:
                return False, 0
            bucket.append(now)
            return True, max(limit - len(bucket), 0)


rate_limiter = InMemoryRateLimiter()


def new_request_id() -> str:
    return str(uuid4())


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def request_id_from(request: Request, settings: Settings | None = None) -> str:
    cfg = settings or get_settings()
    return request.headers.get(cfg.request_id_header) or request.headers.get("X-Request-ID") or new_request_id()


def json_log(event: str, **fields: Any) -> None:
    """Emit one structured operational log line with masked payload fields."""

    settings = get_settings()
    payload = {
        "ts": dt.datetime.now(dt.UTC).isoformat(),
        "event": event,
        **fields,
    }
    if settings.mask_pii_in_logs:
        payload = mask_payload(payload)
    print(json.dumps(payload, ensure_ascii=False, default=str))


def _provided_api_key(request: Request) -> str:
    header_key = request.headers.get("X-Sahayak-API-Key", "")
    if header_key:
        return header_key.strip()
    authorization = request.headers.get("Authorization", "")
    if authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return ""


def _key_role(provided_key: str, settings: Settings) -> str | None:
    if not provided_key:
        return None
    admin_keys = [settings.dashboard_admin_key, settings.dashboard_api_key]
    for key in admin_keys:
        if key and hmac.compare_digest(provided_key, key):
            return "admin"
    if settings.dashboard_readonly_key and hmac.compare_digest(
        provided_key,
        settings.dashboard_readonly_key,
    ):
        return "viewer"
    return None


def requires_dashboard_auth(request: Request, settings: Settings) -> bool:
    if not request.url.path.startswith("/api"):
        return False
    if not settings.dashboard_auth_required and request.method in SAFE_METHODS:
        return False
    if not settings.dashboard_auth_required and settings.demo_mode:
        return request.method not in SAFE_METHODS and bool(
            settings.dashboard_api_key
            or settings.dashboard_admin_key
            or settings.dashboard_readonly_key
        )
    return True


def authorize_dashboard_request(request: Request, settings: Settings | None = None) -> AuthDecision:
    cfg = settings or get_settings()
    if not requires_dashboard_auth(request, cfg):
        return AuthDecision(allowed=True, role="demo")

    role = _key_role(_provided_api_key(request), cfg)
    if not role:
        return AuthDecision(allowed=False)
    if request.method not in SAFE_METHODS and role != "admin":
        return AuthDecision(
            allowed=False,
            role=role,
            status_code=403,
            detail="Admin role required",
        )
    requested_role = request.headers.get("X-Sahayak-Role")
    if requested_role and requested_role not in {"viewer", "operator", "admin"}:
        return AuthDecision(
            allowed=False,
            role=role,
            status_code=403,
            detail="Unsupported role",
        )
    return AuthDecision(allowed=True, role=role)


def _twilio_url_for_validation(request: Request, settings: Settings) -> str:
    base = settings.base_url.rstrip("/")
    path = request.url.path
    query = request.url.query
    return f"{base}{path}" + (f"?{query}" if query else "")


def validate_twilio_request(
    request: Request,
    form: FormData,
    settings: Settings | None = None,
) -> bool:
    """Validate Twilio webhook signature when enabled."""

    cfg = settings or get_settings()
    if not cfg.validate_twilio_signatures:
        return True
    signature = request.headers.get("X-Twilio-Signature", "")
    if not signature or not cfg.twilio_auth_token:
        return False
    validator = RequestValidator(cfg.twilio_auth_token)
    form_values = {key: str(value) for key, value in form.multi_items()}
    return bool(
        validator.validate(
            _twilio_url_for_validation(request, cfg),
            form_values,
            signature,
        )
    )

from __future__ import annotations

from starlette.datastructures import FormData
from starlette.requests import Request
from twilio.request_validator import RequestValidator

from backend.config import Settings
from backend.persistence.pii import mask_payload, mask_phone_number, mask_sensitive_text
from backend.security import authorize_dashboard_request, validate_twilio_request


def make_request(
    path: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    query_string: bytes = b"",
) -> Request:
    return Request(
        {
            "type": "http",
            "method": method,
            "path": path,
            "headers": [
                (key.lower().encode("latin-1"), value.encode("latin-1"))
                for key, value in (headers or {}).items()
            ],
            "query_string": query_string,
            "server": ("testserver", 80),
            "scheme": "https",
            "client": ("127.0.0.1", 12345),
        }
    )


def test_pii_helpers_mask_phone_email_and_payload() -> None:
    assert mask_phone_number("+919876543210").endswith("3210")
    assert mask_phone_number("+919876543210").startswith("*")
    masked = mask_sensitive_text("Call +919876543210 or person@example.com now")
    assert "+919876543210" not in masked
    assert "person@example.com" not in masked

    payload = mask_payload(
        {
            "caller_number": "+919876543210",
            "summary": "Citizen called from +919812345678",
        }
    )
    assert payload["caller_number"].endswith("3210")
    assert "+919812345678" not in payload["summary"]


def test_dashboard_auth_allows_admin_and_blocks_viewer_mutation() -> None:
    settings = Settings(
        demo_mode=False,
        dashboard_auth_required=True,
        dashboard_admin_key="admin-secret",
        dashboard_readonly_key="viewer-secret",
    )

    admin_request = make_request(
        "/api/agent/toggle",
        method="POST",
        headers={"X-Sahayak-API-Key": "admin-secret"},
    )
    viewer_request = make_request(
        "/api/agent/toggle",
        method="POST",
        headers={"X-Sahayak-API-Key": "viewer-secret"},
    )
    missing_request = make_request("/api/agents", method="GET")

    assert authorize_dashboard_request(admin_request, settings).allowed is True
    viewer_decision = authorize_dashboard_request(viewer_request, settings)
    assert viewer_decision.allowed is False
    assert viewer_decision.status_code == 403
    missing_decision = authorize_dashboard_request(missing_request, settings)
    assert missing_decision.allowed is False
    assert missing_decision.status_code == 401


def test_twilio_signature_validation_accepts_valid_signature() -> None:
    settings = Settings(
        base_url="https://sahayak.example",
        twilio_auth_token="twilio-token",
        validate_twilio_signatures=True,
    )
    form = FormData({"CallSid": "CA123", "From": "+919876543210"})
    signature = RequestValidator("twilio-token").compute_signature(
        "https://sahayak.example/twilio/status",
        {"CallSid": "CA123", "From": "+919876543210"},
    )
    request = make_request(
        "/twilio/status",
        method="POST",
        headers={"X-Twilio-Signature": signature},
    )

    assert validate_twilio_request(request, form, settings) is True


def test_twilio_signature_validation_rejects_bad_signature() -> None:
    settings = Settings(
        base_url="https://sahayak.example",
        twilio_auth_token="twilio-token",
        validate_twilio_signatures=True,
    )
    request = make_request(
        "/twilio/status",
        method="POST",
        headers={"X-Twilio-Signature": "bad-signature"},
    )

    assert validate_twilio_request(request, FormData({"CallSid": "CA123"}), settings) is False

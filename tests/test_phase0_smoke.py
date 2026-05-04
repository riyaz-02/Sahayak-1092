from __future__ import annotations

import importlib
import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def _missing_modules(*module_names: str) -> list[str]:
    return [name for name in module_names if importlib.util.find_spec(name) is None]


def test_core_backend_modules_import_without_service_dependencies() -> None:
    from backend.api.health import build_health_payload
    from backend.config import get_settings
    from backend.intelligence.safety_rules import evaluate_handover
    from backend.intelligence.schemas import CallAnalysis
    from backend.routing.officer_router import score_agent
    from backend.voice.audio_codec import mulaw_to_pcm16, pcm16_to_mulaw

    settings = get_settings()
    assert settings.app_name == "Sahayak 1092"
    assert build_health_payload(active_calls=2)["active_calls"] == 2

    decision = evaluate_handover(
        CallAnalysis(caller_wants_human=True),
        current_attempt_count=0,
    )
    assert decision.needs_handover is True

    score = score_agent(
        {
            "languages": ["kannada", "english"],
            "specialties": ["theft"],
            "avg_wait_sec": 15,
            "current_load": 0,
        },
        call_language="kannada",
        category="theft",
    )
    assert score > 0.8

    pcm = mulaw_to_pcm16(b"\xff" * 160)
    assert isinstance(pcm, bytes)
    assert isinstance(pcm16_to_mulaw(pcm), bytes)


def test_backend_app_imports_when_runtime_dependencies_are_installed() -> None:
    missing = _missing_modules("fastapi", "twilio", "openai", "dotenv", "httpx", "supabase")
    if missing:
        pytest.skip(f"Install runtime dependencies first: missing {', '.join(missing)}")

    module = importlib.import_module("backend.app")
    assert module.app.title == "Sahayak 1092"


def test_dashboard_imports_when_runtime_dependencies_are_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    missing = _missing_modules("streamlit", "requests")
    if missing:
        pytest.skip(f"Install dashboard dependencies first: missing {', '.join(missing)}")

    monkeypatch.setenv("SAHAYAK_API_URL", "http://localhost:8000")
    module = importlib.import_module("dashboard.app")
    assert module.API_BASE == "http://localhost:8000"


def test_env_example_contains_no_real_secrets() -> None:
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")

    assert "your_openai_api_key" not in env_example
    assert "your_supabase_anon_key" not in env_example
    assert "sk-" not in env_example
    assert "TWILIO_AUTH_TOKEN=" in env_example
    assert "OPENAI_API_KEY=" in env_example
    assert "SUPABASE_KEY=" in env_example


def test_developer_commands_are_documented() -> None:
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")

    for target in ["install:", "dev-backend:", "dev-dashboard:", "test:", "lint:", "compile:"]:
        assert target in makefile

from __future__ import annotations

from backend.config import Settings
from backend.intelligence.schemas import CallPhase, CallState
from backend.persistence.complaints import ComplaintRegistry
from backend.persistence.repository import CallStateRepository
from backend.voice import scripted_demo


def test_scripted_demo_confirms_mobile_theft_without_llm(monkeypatch) -> None:
    repo = CallStateRepository(Settings(supabase_url="", supabase_key="", redis_url=""))
    registry = ComplaintRegistry(Settings(supabase_url="", supabase_key="", redis_url=""))
    monkeypatch.setattr(scripted_demo, "get_call_repository", lambda: repo)
    monkeypatch.setattr(scripted_demo, "get_complaint_registry", lambda: registry)

    state = CallState(call_sid="script-demo-1", caller_number="+919999999999", language="hindi")
    repo.create_call_state(state)

    result = scripted_demo.process_scripted_voice_turn(
        call_state=state,
        text="Mera mobile Majestic bus stand par chori ho gaya",
        settings=Settings(voice_scripted_demo_enabled=True, voice_script_language="hindi"),
    )

    assert result["action"] == "continue"
    assert "Majestic bus stand" in result["response_text"]
    assert "क्या यह जानकारी सही है" in result["response_text"]
    assert state.current_phase == CallPhase.VACHAN_PENDING.value
    assert state.transcript[-1]["text"] == result["response_text"]


def test_scripted_demo_registers_complaint_after_confirmation(monkeypatch) -> None:
    repo = CallStateRepository(Settings(supabase_url="", supabase_key="", redis_url=""))
    registry = ComplaintRegistry(Settings(supabase_url="", supabase_key="", redis_url=""))
    monkeypatch.setattr(scripted_demo, "get_call_repository", lambda: repo)
    monkeypatch.setattr(scripted_demo, "get_complaint_registry", lambda: registry)

    state = CallState(call_sid="script-demo-2", caller_number="+919999999999", language="hindi")
    repo.create_call_state(state)

    scripted_demo.process_scripted_voice_turn(
        call_state=state,
        text="Mera mobile Majestic bus stand par chori ho gaya",
        settings=Settings(voice_scripted_demo_enabled=True, voice_script_language="hindi"),
    )
    result = scripted_demo.process_scripted_voice_turn(
        call_state=state,
        text="haan sahi hai",
        settings=Settings(voice_scripted_demo_enabled=True, voice_script_language="hindi"),
    )

    assert result["action"] == "resolve"
    assert state.complaint_registered is True
    assert state.complaint_reference_id
    assert state.current_phase == CallPhase.RESOLVED.value
    assert state.complaint_reference_id in result["response_text"]
    assert registry.get_by_call_sid("script-demo-2") is not None


def test_scripted_demo_supports_kannada_mobile_theft(monkeypatch) -> None:
    repo = CallStateRepository(Settings(supabase_url="", supabase_key="", redis_url=""))
    registry = ComplaintRegistry(Settings(supabase_url="", supabase_key="", redis_url=""))
    monkeypatch.setattr(scripted_demo, "get_call_repository", lambda: repo)
    monkeypatch.setattr(scripted_demo, "get_complaint_registry", lambda: registry)

    state = CallState(call_sid="script-demo-kn-1", caller_number="+919999999999", language="hindi")
    repo.create_call_state(state)

    greeting = scripted_demo.scripted_demo_greeting(
        settings=Settings(voice_scripted_demo_enabled=True, voice_script_language="karnataka")
    )
    result = scripted_demo.process_scripted_voice_turn(
        call_state=state,
        text="Nanna mobile Majestic bus stand hattira kallatana agide",
        settings=Settings(voice_scripted_demo_enabled=True, voice_script_language="karnataka"),
    )

    assert "ನಮಸ್ಕಾರ" in greeting
    assert result["action"] == "continue"
    assert result["analysis"]["language"] == "kannada"
    assert "Majestic bus stand" in result["response_text"]
    assert "ಈ ಮಾಹಿತಿ ಸರಿಯೇ" in result["response_text"]
    assert state.language == "kannada"
    assert state.current_phase == CallPhase.VACHAN_PENDING.value


def test_scripted_demo_auto_detects_romanized_kannada(monkeypatch) -> None:
    repo = CallStateRepository(Settings(supabase_url="", supabase_key="", redis_url=""))
    registry = ComplaintRegistry(Settings(supabase_url="", supabase_key="", redis_url=""))
    monkeypatch.setattr(scripted_demo, "get_call_repository", lambda: repo)
    monkeypatch.setattr(scripted_demo, "get_complaint_registry", lambda: registry)

    state = CallState(call_sid="script-demo-auto-kn", caller_number="+919999999999", language="hindi")
    repo.create_call_state(state)

    result = scripted_demo.process_scripted_voice_turn(
        call_state=state,
        text="Nanna mobile Majestic bus stand hattira kallatana agide",
        settings=Settings(voice_scripted_demo_enabled=True, voice_script_language="auto"),
    )

    assert scripted_demo.scripted_demo_stt_language(
        state,
        Settings(voice_scripted_demo_enabled=True, voice_script_language="auto"),
    ) == "unknown"
    assert scripted_demo.infer_scripted_language_from_text("howdu sari", fallback="hindi") == "kannada"
    assert result["analysis"]["language"] == "kannada"
    assert "ಈ ಮಾಹಿತಿ ಸರಿಯೇ" in result["response_text"]


def test_scripted_demo_preview_has_no_persistence_side_effects(monkeypatch) -> None:
    repo = CallStateRepository(Settings(supabase_url="", supabase_key="", redis_url=""))
    registry = ComplaintRegistry(Settings(supabase_url="", supabase_key="", redis_url=""))
    monkeypatch.setattr(scripted_demo, "get_call_repository", lambda: repo)
    monkeypatch.setattr(scripted_demo, "get_complaint_registry", lambda: registry)

    preview = scripted_demo.preview_scripted_voice_turn(
        text="Nanna mobile Majestic bus stand hattira kallatana agide",
        settings=Settings(voice_scripted_demo_enabled=True, voice_script_language="auto"),
    )

    assert preview["detected_script_language"] == "kannada"
    assert "ಈ ಮಾಹಿತಿ ಸರಿಯೇ" in preview["response_text"]
    assert repo.fetch_active_calls() == []
    assert registry.list_complaints() == []


def test_scripted_demo_registers_kannada_confirmation(monkeypatch) -> None:
    repo = CallStateRepository(Settings(supabase_url="", supabase_key="", redis_url=""))
    registry = ComplaintRegistry(Settings(supabase_url="", supabase_key="", redis_url=""))
    monkeypatch.setattr(scripted_demo, "get_call_repository", lambda: repo)
    monkeypatch.setattr(scripted_demo, "get_complaint_registry", lambda: registry)

    state = CallState(call_sid="script-demo-kn-2", caller_number="+919999999999", language="kannada")
    repo.create_call_state(state)

    scripted_demo.process_scripted_voice_turn(
        call_state=state,
        text="Nanna mobile Majestic bus stand hattira kallatana agide",
        settings=Settings(voice_scripted_demo_enabled=True, voice_script_language="kannada"),
    )
    result = scripted_demo.process_scripted_voice_turn(
        call_state=state,
        text="howdu sari",
        settings=Settings(voice_scripted_demo_enabled=True, voice_script_language="kannada"),
    )

    assert result["action"] == "resolve"
    assert "ನಿಮ್ಮ ದೂರು ದಾಖಲಾಗಿದೆ" in result["response_text"]
    assert state.complaint_reference_id in result["response_text"]
    assert state.current_phase == CallPhase.RESOLVED.value
    assert registry.get_by_call_sid("script-demo-kn-2") is not None

from __future__ import annotations

import pytest

from backend.config import Settings
from backend.intelligence.embeddings import DeterministicEmbeddingProvider
from backend.intelligence.schemas import CallAnalysis, CallPhase, CallState
from backend.intelligence.similarity import (
    SimilarityService,
    deterministic_seed_cases,
    generate_seed_case_embeddings,
    seed_demo_vector_cases,
    urgency_band,
)


@pytest.mark.asyncio
async def test_seed_resolved_cases_receive_deterministic_embeddings() -> None:
    cases = await generate_seed_case_embeddings(DeterministicEmbeddingProvider())

    assert cases
    assert len(cases) >= 40
    assert len(cases[0]["embedding"]) == 1536
    assert cases[0]["urgency_band"] == "medium"


def test_competition_seed_dataset_is_normalized_for_similarity() -> None:
    cases = deterministic_seed_cases()
    categories = {case["category"] for case in cases}

    assert len(cases) >= 40
    assert "cyber" in categories
    assert "domestic" in categories
    assert "accident" in categories
    assert "harassment" in categories
    assert "civic" in categories
    assert "cyber_fraud" not in categories
    assert any(case["language"] == "kannada" for case in cases)
    assert any(case["dialect"] == "kolkata-urban" for case in cases)


@pytest.mark.asyncio
async def test_seed_vector_cases_skips_existing_summaries(monkeypatch: pytest.MonkeyPatch) -> None:
    from backend.intelligence import similarity

    inserted: list[dict] = []
    first_case = deterministic_seed_cases()[0]

    monkeypatch.setattr(
        similarity.db,
        "get_all_resolved_cases",
        lambda limit=2000, include_embedding=False: [{"summary": first_case["summary"]}],
    )

    def fake_insert_resolved_case(**kwargs):
        inserted.append(kwargs)
        return {"id": f"case-{len(inserted)}", **kwargs}

    monkeypatch.setattr(similarity.db, "insert_resolved_case", fake_insert_resolved_case)

    result = await seed_demo_vector_cases(provider=DeterministicEmbeddingProvider())

    assert result["attempted"] >= 40
    assert result["skipped_existing"] == 1
    assert result["inserted"] == result["attempted"] - 1
    assert all(item["summary"] != first_case["summary"] for item in inserted)


@pytest.mark.asyncio
async def test_mobile_theft_matches_seeded_human_resolved_case() -> None:
    service = SimilarityService(
        settings=Settings(
            openai_api_key="",
            embedding_provider="deterministic",
            similarity_match_threshold=0.7,
        ),
        provider=DeterministicEmbeddingProvider(),
    )
    analysis = CallAnalysis(
        language="english",
        category="theft",
        urgency=0.62,
        confidence=0.9,
        summary="Caller reports mobile phone theft at Majestic bus stand.",
        raw_text="My mobile phone was stolen while boarding the bus at Majestic.",
    )
    call_state = CallState(call_sid="phase4-similarity")
    call_state.transcript.append({"role": "caller", "text": analysis.raw_text})

    match = await service.find_match(analysis, call_state)

    assert match is not None
    assert match.retrieval_source == "local_fallback"
    assert match.matched_case["category"] == "theft"
    assert "mobile_theft" in match.matched_case["tags"]
    assert match.similarity_score >= 0.7
    assert "similar resolved case" in match.adapted_resolution.lower()


@pytest.mark.asyncio
async def test_pipeline_response_exposes_similarity_match(monkeypatch: pytest.MonkeyPatch) -> None:
    from backend import decision_engine

    decision_engine.call_repository.reset_for_tests()
    decision_engine.active_calls.clear()
    monkeypatch.setattr(
        decision_engine,
        "settings",
        Settings(
            openai_api_key="",
            analysis_provider="deterministic",
            embedding_provider="deterministic",
            similarity_match_threshold=0.7,
        ),
    )

    async def fake_response(
        call_state: CallState,
        analysis: CallAnalysis,
        resolution: str | None = None,
    ) -> str:
        return "I found a similar resolved case. Is this correct?"

    monkeypatch.setattr(decision_engine, "generate_response", fake_response)

    result = await decision_engine.process_caller_input(
        call_sid="phase4-pipeline",
        text="My mobile phone was stolen while boarding the bus at Majestic.",
        caller_number="+919111111111",
    )

    assert result["action"] == "continue"
    assert result["similarity"]["retrieval_source"] == "local_fallback"
    assert result["similarity"]["similarity_score"] >= 0.7
    assert result["call_state"]["matched_case_id"]
    assert result["call_state"]["current_phase"] == CallPhase.VACHAN_PENDING.value


@pytest.mark.asyncio
async def test_confirmed_ai_resolution_is_written_to_knowledge_base(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from backend import decision_engine

    decision_engine.call_repository.reset_for_tests()
    decision_engine.active_calls.clear()
    monkeypatch.setattr(
        decision_engine,
        "settings",
        Settings(openai_api_key="", analysis_provider="deterministic"),
    )

    captured: dict = {}

    def fake_insert_resolved_case(**kwargs):
        captured.update(kwargs)
        return {"id": "learned-case-1", **kwargs}

    async def fake_response(
        call_state: CallState,
        analysis: CallAnalysis,
        resolution: str | None = None,
    ) -> str:
        return "Your complaint has been registered."

    monkeypatch.setattr(decision_engine.db, "insert_resolved_case", fake_insert_resolved_case)
    monkeypatch.setattr(decision_engine, "generate_response", fake_response)

    state = decision_engine.get_or_create_call("phase4-learning", "+919222222222")
    state.current_phase = CallPhase.VACHAN_PENDING.value
    state.language = "english"
    state.ai_summary = "Caller reports mobile phone theft."
    state.resolution = "Register phone theft complaint and advise SIM blocking."
    state.similar_case = {"category": "theft"}
    decision_engine.call_repository.update_call_state(state)

    result = await decision_engine.process_caller_input(
        call_sid="phase4-learning",
        text="yes",
        caller_number="+919222222222",
    )

    assert result["action"] == "resolve"
    assert captured["category"] == "theft"
    assert captured["source_call_sid"] == "phase4-learning"
    assert captured["urgency_band"] == urgency_band(result["analysis"]["urgency"])
    assert len(captured["embedding"]) == 1536

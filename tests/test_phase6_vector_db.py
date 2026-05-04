from __future__ import annotations

import pytest

from backend.config import Settings
from backend.intelligence.embeddings import DeterministicEmbeddingProvider
from backend.intelligence.schemas import CallAnalysis, CallState
from backend.intelligence.similarity import (
    SimilarityService,
    backfill_resolved_case_embeddings,
)


def test_supabase_rpc_wrapper_sends_vector_filters(monkeypatch: pytest.MonkeyPatch) -> None:
    from backend import supabase_client as db

    captured: dict = {}

    class FakeRPC:
        data = [{"id": "case-1", "similarity": 0.91}]

        def execute(self):
            return self

    class FakeClient:
        def rpc(self, name: str, params: dict):
            captured["name"] = name
            captured["params"] = params
            return FakeRPC()

    monkeypatch.setattr(db, "get_client", lambda: FakeClient())

    rows = db.match_resolved_cases(
        query_embedding=[0.1] * 1536,
        category="theft",
        language="english",
        dialect="bengaluru",
        urgency_band="medium",
        limit=7,
        threshold=0.12,
    )

    assert rows[0]["id"] == "case-1"
    assert captured["name"] == "match_resolved_cases"
    assert captured["params"]["filter_category"] == "theft"
    assert captured["params"]["filter_language"] == "english"
    assert captured["params"]["filter_dialect"] == "bengaluru"
    assert captured["params"]["filter_urgency_band"] == "medium"
    assert captured["params"]["match_count"] == 7
    assert captured["params"]["match_threshold"] == 0.12
    assert captured["params"]["query_embedding"].startswith("[0.10000000")


@pytest.mark.asyncio
async def test_similarity_service_prefers_vector_db_candidates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from backend.intelligence import similarity

    calls: list[dict] = []

    def fake_match_resolved_cases(**kwargs):
        calls.append(kwargs)
        return [
            {
                "id": "vector-case-1",
                "summary": "Caller reported mobile phone theft at Majestic bus stand.",
                "category": "theft",
                "language": "english",
                "dialect": "",
                "urgency_band": "medium",
                "resolution": "Register FIR and advise SIM blocking.",
                "tags": ["mobile_theft"],
                "similarity": 0.94,
            }
        ]

    def fail_get_all_resolved_cases(*args, **kwargs):
        raise AssertionError("Vector DB path should not fetch all resolved cases")

    monkeypatch.setattr(similarity.db, "match_resolved_cases", fake_match_resolved_cases)
    monkeypatch.setattr(similarity.db, "get_all_resolved_cases", fail_get_all_resolved_cases)

    service = SimilarityService(
        settings=Settings(
            supabase_url="https://example.supabase.co",
            supabase_key="test-key",
            openai_api_key="",
            embedding_provider="deterministic",
            similarity_match_threshold=0.7,
            vector_db_match_threshold=0.1,
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

    match = await service.find_match(analysis, CallState(call_sid="phase6-vector"))

    assert match is not None
    assert match.retrieval_source == "vector_db"
    assert match.matched_case_id == "vector-case-1"
    assert match.similarity_score >= 0.7
    assert calls[0]["category"] == "theft"
    assert calls[0]["language"] == "english"
    assert calls[0]["urgency_band"] == "medium"


@pytest.mark.asyncio
async def test_similarity_service_keeps_local_fallback_when_vector_db_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from backend.intelligence import similarity

    monkeypatch.setattr(similarity.db, "match_resolved_cases", lambda **kwargs: [])

    service = SimilarityService(
        settings=Settings(
            supabase_url="https://example.supabase.co",
            supabase_key="test-key",
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

    match = await service.find_match(analysis, CallState(call_sid="phase6-fallback"))

    assert match is not None
    assert match.retrieval_source == "local_fallback"
    assert match.matched_case["category"] == "theft"


@pytest.mark.asyncio
async def test_backfill_resolved_case_embeddings_updates_missing_cases(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from backend.intelligence import similarity

    updated: dict = {}
    monkeypatch.setattr(
        similarity.db,
        "get_resolved_cases_missing_embeddings",
        lambda limit=100: [
            {
                "id": "missing-embedding-1",
                "summary": "Caller reported mobile phone theft at Majestic bus stand.",
                "category": "theft",
                "language": "english",
                "dialect": "",
                "urgency_band": "medium",
                "resolution": "Register FIR and advise SIM blocking.",
                "tags": ["mobile_theft"],
            }
        ],
    )

    def fake_update(case_id: str, embedding: list[float]):
        updated["case_id"] = case_id
        updated["embedding"] = embedding
        return {"id": case_id}

    monkeypatch.setattr(similarity.db, "update_resolved_case_embedding", fake_update)

    result = await backfill_resolved_case_embeddings(
        provider=DeterministicEmbeddingProvider(),
    )

    assert result == {"attempted": 1, "updated": 1}
    assert updated["case_id"] == "missing-embedding-1"
    assert len(updated["embedding"]) == 1536

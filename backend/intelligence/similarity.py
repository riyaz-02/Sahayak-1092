"""Smart Similarity Detection for resolved-case retrieval."""

from __future__ import annotations

import ast
from typing import Any

from backend.config import Settings, get_settings
from backend.intelligence.embeddings import (
    EmbeddingProvider,
    cosine_similarity,
    get_embedding_provider,
)
from backend.intelligence.schemas import CallAnalysis, CallState, SimilarityMatch
from backend import supabase_client as db


def urgency_band(urgency: float | None) -> str:
    value = urgency if urgency is not None else 0.5
    if value >= 0.9:
        return "critical"
    if value >= 0.7:
        return "high"
    if value >= 0.4:
        return "medium"
    return "low"


def case_text(case: dict[str, Any]) -> str:
    tags = " ".join(case.get("tags") or [])
    return " ".join(
        part
        for part in [
            case.get("category", ""),
            case.get("language", ""),
            case.get("dialect", ""),
            case.get("urgency_band", ""),
            tags,
            case.get("summary", ""),
            case.get("resolution", ""),
        ]
        if part
    )


def query_text(analysis: CallAnalysis, call_state: CallState | None = None) -> str:
    transcript_text = ""
    if call_state:
        transcript_text = " ".join(
            item.get("text", "") for item in call_state.transcript[-4:] if item.get("role") == "caller"
        )
    return " ".join(
        part
        for part in [
            analysis.category,
            analysis.language,
            analysis.dialect,
            urgency_band(analysis.urgency),
            analysis.summary,
            analysis.raw_text,
            transcript_text,
        ]
        if part
    )


def parse_embedding(value: Any) -> list[float] | None:
    if isinstance(value, list):
        return [float(item) for item in value]
    if isinstance(value, str) and value.strip():
        try:
            parsed = ast.literal_eval(value)
            if isinstance(parsed, list):
                return [float(item) for item in parsed]
        except Exception:
            return None
    return None


def serializable_embedding(vector: list[float]) -> list[float]:
    return [round(value, 8) for value in vector]


def _summary_key(value: str | None) -> str:
    return " ".join(str(value or "").lower().split())


def deterministic_seed_cases() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for index, case in enumerate(db.SEED_RESOLVED_CASES):
        row = dict(case)
        row.setdefault("id", f"seed-resolved-case-{index + 1}")
        row.setdefault("source_call_sid", f"seed:{index + 1:03d}")
        row.setdefault("dialect", "")
        row.setdefault("urgency_band", _case_urgency_band(row))
        cases.append(row)
    return cases


async def generate_case_embedding(
    case: dict[str, Any],
    provider: EmbeddingProvider | None = None,
) -> list[float]:
    embedder = provider or get_embedding_provider()
    return await embedder.embed_text(case_text(case))


async def hydrate_case_embeddings(
    cases: list[dict[str, Any]],
    provider: EmbeddingProvider | None = None,
) -> list[dict[str, Any]]:
    embedder = provider or get_embedding_provider()
    hydrated: list[dict[str, Any]] = []
    for case in cases:
        row = dict(case)
        embedding = parse_embedding(row.get("embedding"))
        if not embedding:
            embedding = await generate_case_embedding(row, embedder)
            row["embedding"] = serializable_embedding(embedding)
        hydrated.append(row)
    return hydrated


async def get_cases_for_similarity(
    limit: int = 100,
    provider: EmbeddingProvider | None = None,
) -> list[dict[str, Any]]:
    try:
        cases = db.get_all_resolved_cases(limit=limit, include_embedding=True)
    except Exception:
        cases = []
    if not cases:
        cases = deterministic_seed_cases()
    return await hydrate_case_embeddings(cases, provider=provider)


def _case_urgency_band(case: dict[str, Any]) -> str:
    if case.get("urgency_band"):
        return str(case["urgency_band"])
    category = (case.get("category") or "general").lower()
    if category in {"medical", "fire"}:
        return "critical"
    if category in {"accident", "domestic", "missing_person"}:
        return "high"
    if category in {"theft", "cyber", "suspicious_activity", "harassment", "civic"}:
        return "medium"
    return "low"


def _adjacent_band_score(query_band: str, case_band: str) -> float:
    order = {"low": 0, "medium": 1, "high": 2, "critical": 3}
    if query_band not in order or case_band not in order:
        return 0.65
    distance = abs(order[query_band] - order[case_band])
    if distance == 0:
        return 1.0
    if distance == 1:
        return 0.78
    return 0.45


def _metadata_score(analysis: CallAnalysis, case: dict[str, Any]) -> dict[str, float]:
    case_category = (case.get("category") or "general").lower()
    case_language = (case.get("language") or "unknown").lower()
    case_dialect = (case.get("dialect") or "").lower()
    case_tags = {str(tag).lower() for tag in case.get("tags") or []}
    query_band = urgency_band(analysis.urgency)
    case_band = _case_urgency_band(case)

    category_score = 1.0 if analysis.category == case_category else 0.15
    if analysis.category in case_tags:
        category_score = max(category_score, 0.8)

    language_score = 1.0 if analysis.language == case_language else 0.72
    if analysis.language == "unknown" or case_language == "unknown":
        language_score = 0.62

    if analysis.dialect and case_dialect:
        dialect_score = 1.0 if analysis.dialect.lower() == case_dialect else 0.45
    else:
        dialect_score = 0.72

    band_score = _adjacent_band_score(query_band, case_band)
    combined = (
        0.48 * category_score
        + 0.22 * language_score
        + 0.12 * dialect_score
        + 0.18 * band_score
    )
    return {
        "category": category_score,
        "language": language_score,
        "dialect": dialect_score,
        "urgency_band": band_score,
        "combined": combined,
    }


def _blend_score(vector_score: float, metadata_score: float) -> float:
    normalized_vector = (vector_score + 1.0) / 2.0
    blended = 0.72 * normalized_vector + 0.28 * metadata_score
    return max(0.0, min(1.0, blended))


class SimilarityService:
    """Retrieve and adapt past human-resolved cases."""

    def __init__(
        self,
        settings: Settings | None = None,
        provider: EmbeddingProvider | None = None,
        llm_client: Any | None = None,
    ):
        self.settings = settings or get_settings()
        self.provider = provider or get_embedding_provider(self.settings)
        self.llm_client = llm_client

    async def find_match(
        self,
        analysis: CallAnalysis,
        call_state: CallState | None = None,
        cases: list[dict[str, Any]] | None = None,
    ) -> SimilarityMatch | None:
        query_embedding = await self.provider.embed_text(query_text(analysis, call_state))
        retrieval_source = "local_fallback"
        retrieval_attempts: list[dict[str, Any]] = []

        if cases is not None:
            candidate_cases = cases
        else:
            candidate_cases, retrieval_attempts = self._get_vector_db_candidates(
                query_embedding=query_embedding,
                analysis=analysis,
            )
            if candidate_cases:
                retrieval_source = "vector_db"
            else:
                candidate_cases = await get_cases_for_similarity(provider=self.provider)

        if not candidate_cases:
            return None

        scored: list[tuple[float, dict[str, Any], dict[str, Any]]] = []

        for case in candidate_cases:
            vector_score = self._vector_score_from_case(case, query_embedding)
            if vector_score is None:
                embedding = await generate_case_embedding(case, self.provider)
                vector_score = cosine_similarity(query_embedding, embedding)

            metadata = _metadata_score(analysis, case)
            final_score = _blend_score(vector_score, metadata["combined"])
            scored.append(
                (
                    final_score,
                    case,
                    {
                        "vector_score": round(vector_score, 4),
                        "metadata": metadata,
                        "query_urgency_band": urgency_band(analysis.urgency),
                        "case_urgency_band": _case_urgency_band(case),
                        "source": retrieval_source,
                        "vector_db_attempts": retrieval_attempts,
                    },
                )
            )

        scored.sort(key=lambda item: item[0], reverse=True)
        score, case, signals = scored[0]
        if score < self.settings.similarity_match_threshold:
            return None

        adapted = await self.adapt_resolution(analysis, case)
        return SimilarityMatch(
            matched_case_id=str(case.get("id") or case.get("case_id") or ""),
            matched_case={key: value for key, value in case.items() if key != "embedding"},
            similarity_score=round(score, 4),
            adapted_resolution=adapted,
            retrieval_source=retrieval_source,
            retrieval_signals=signals,
        )

    def _get_vector_db_candidates(
        self,
        query_embedding: list[float],
        analysis: CallAnalysis,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        if not self.settings.supabase_configured:
            return [], []

        query_band = urgency_band(analysis.urgency)
        attempts = [
            {
                "category": analysis.category,
                "language": analysis.language,
                "dialect": analysis.dialect,
                "urgency_band": query_band,
            },
            {
                "category": analysis.category,
                "language": analysis.language,
                "dialect": None,
                "urgency_band": query_band,
            },
            {
                "category": analysis.category,
                "language": None,
                "dialect": None,
                "urgency_band": query_band,
            },
            {
                "category": analysis.category,
                "language": None,
                "dialect": None,
                "urgency_band": None,
            },
            {
                "category": None,
                "language": None,
                "dialect": None,
                "urgency_band": None,
            },
        ]
        audit_attempts: list[dict[str, Any]] = []
        for filters in attempts:
            rows = db.match_resolved_cases(
                query_embedding=serializable_embedding(query_embedding),
                category=filters["category"],
                language=filters["language"],
                dialect=filters["dialect"],
                urgency_band=filters["urgency_band"],
                limit=self.settings.vector_search_limit,
                threshold=self.settings.vector_db_match_threshold,
            )
            audit_attempts.append({**filters, "count": len(rows)})
            if rows:
                return rows, audit_attempts
        return [], audit_attempts

    @staticmethod
    def _vector_score_from_case(
        case: dict[str, Any],
        query_embedding: list[float],
    ) -> float | None:
        if case.get("similarity") is not None:
            return float(case["similarity"])
        embedding = parse_embedding(case.get("embedding"))
        if embedding and len(embedding) == len(query_embedding):
            return cosine_similarity(query_embedding, embedding)
        return None

    async def adapt_resolution(self, analysis: CallAnalysis, case: dict[str, Any]) -> str:
        resolution = str(case.get("resolution") or "")
        if not resolution:
            return "Sahayak will register the issue and guide you through the next safe step."

        if not self.settings.openai_api_key:
            return self._deterministic_adaptation(analysis, resolution)

        try:
            if not self.llm_client:
                from openai import AsyncOpenAI

                self.llm_client = AsyncOpenAI(
                    api_key=self.settings.openai_api_key,
                    base_url=self.settings.openai_base_url,
                )
            response = await self.llm_client.chat.completions.create(
                model=self.settings.llm_model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Adapt the already-retrieved helpline resolution to the current caller. "
                            "Do not search or invent a new case. Keep it concise, practical, and in "
                            f"{analysis.language}."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Current issue: {analysis.summary}\n"
                            f"Category: {analysis.category}\n"
                            f"Retrieved resolution: {resolution}"
                        ),
                    },
                ],
                temperature=0.2,
                max_tokens=220,
            )
            return response.choices[0].message.content.strip()
        except Exception as exc:
            print(f"[WARN] Similarity resolution adaptation fallback activated: {exc}")
            return self._deterministic_adaptation(analysis, resolution)

    @staticmethod
    def _deterministic_adaptation(analysis: CallAnalysis, resolution: str) -> str:
        prefix_by_language = {
            "kannada": "ಇದೇ ರೀತಿಯ ಪ್ರಕರಣದ ಆಧಾರದ ಮೇಲೆ: ",
            "hindi": "इसी तरह के पहले हल हुए मामले के आधार पर: ",
            "english": "Based on a similar resolved case: ",
        }
        prefix = prefix_by_language.get(analysis.language, prefix_by_language["english"])
        return prefix + resolution


async def find_similar_resolved_case(
    analysis: CallAnalysis,
    call_state: CallState | None = None,
    settings: Settings | None = None,
    llm_client: Any | None = None,
) -> SimilarityMatch | None:
    return await SimilarityService(settings=settings, llm_client=llm_client).find_match(
        analysis=analysis,
        call_state=call_state,
    )


async def generate_seed_case_embeddings(
    provider: EmbeddingProvider | None = None,
) -> list[dict[str, Any]]:
    return await hydrate_case_embeddings(deterministic_seed_cases(), provider=provider)


async def seed_demo_vector_cases(
    provider: EmbeddingProvider | None = None,
) -> dict[str, Any]:
    """Insert demo resolved cases with embeddings into Supabase."""

    cases = await generate_seed_case_embeddings(provider=provider)
    existing_summaries = {
        _summary_key(case.get("summary"))
        for case in db.get_all_resolved_cases(limit=2000)
        if case.get("summary")
    }
    inserted = 0
    skipped_existing = 0
    for case in cases:
        row = dict(case)
        if _summary_key(row.get("summary")) in existing_summaries:
            skipped_existing += 1
            continue
        row.pop("id", None)
        result = db.insert_resolved_case(
            summary=row["summary"],
            category=row["category"],
            language=row["language"],
            dialect=row.get("dialect", ""),
            urgency_band=row.get("urgency_band", "medium"),
            resolution=row["resolution"],
            tags=row.get("tags", []),
            source_call_sid=row.get("source_call_sid"),
            embedding=row.get("embedding"),
        )
        if result:
            inserted += 1
            existing_summaries.add(_summary_key(row.get("summary")))
    return {"attempted": len(cases), "inserted": inserted, "skipped_existing": skipped_existing}


async def backfill_resolved_case_embeddings(
    limit: int = 100,
    provider: EmbeddingProvider | None = None,
) -> dict[str, Any]:
    """Generate and persist embeddings for resolved cases that are missing them."""

    embedder = provider or get_embedding_provider()
    cases = db.get_resolved_cases_missing_embeddings(limit=limit)
    updated = 0
    for case in cases:
        embedding = await generate_case_embedding(case, embedder)
        result = db.update_resolved_case_embedding(
            case_id=str(case["id"]),
            embedding=serializable_embedding(embedding),
        )
        if result:
            updated += 1
    return {"attempted": len(cases), "updated": updated}

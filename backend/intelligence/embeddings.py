"""Embedding providers for Smart Similarity Detection."""

from __future__ import annotations

import hashlib
import math
import re
from abc import ABC, abstractmethod

from backend.config import Settings, get_settings


EMBEDDING_DIMENSION = 1536


def normalize_vector(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [value / norm for value in vector]


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return sum(a * b for a, b in zip(left, right)) / (left_norm * right_norm)


def tokenize_for_embedding(text: str) -> list[str]:
    """Tokenize multilingual text for deterministic local embeddings."""

    lowered = text.lower()
    words = re.findall(r"[\w\u0900-\u097f\u0c80-\u0cff]+", lowered)
    ngrams: list[str] = []
    for word in words:
        if len(word) >= 4:
            ngrams.extend(word[index : index + 4] for index in range(len(word) - 3))
    return words + ngrams


class EmbeddingProvider(ABC):
    """Common embedding provider interface."""

    dimension: int = EMBEDDING_DIMENSION

    @abstractmethod
    async def embed_text(self, text: str) -> list[float]:
        raise NotImplementedError


class DeterministicEmbeddingProvider(EmbeddingProvider):
    """Offline hashing-trick embedding for tests and demos.

    It is not semantic like a production embedding model, but it is stable,
    fast, multilingual-safe, and good enough for matching repeated operational
    issue patterns such as mobile theft, road accidents, fire, and fraud.
    """

    def __init__(self, dimension: int = EMBEDDING_DIMENSION):
        self.dimension = dimension

    async def embed_text(self, text: str) -> list[float]:
        vector = [0.0] * self.dimension
        tokens = tokenize_for_embedding(text)
        if not tokens:
            return vector

        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimension
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            weight = 1.0 + min(len(token), 16) / 32.0
            vector[index] += sign * weight

        return normalize_vector(vector)


class OpenAIEmbeddingProvider(EmbeddingProvider):
    """OpenAI-compatible embedding provider for production deployments."""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.dimension = self.settings.embedding_dimension
        self._client = None

    async def embed_text(self, text: str) -> list[float]:
        if not self._client:
            from openai import AsyncOpenAI

            self._client = AsyncOpenAI(
                api_key=self.settings.openai_api_key,
                base_url=self.settings.openai_base_url,
            )

        response = await self._client.embeddings.create(
            model=self.settings.embedding_model,
            input=text,
        )
        return [float(value) for value in response.data[0].embedding]


def get_embedding_provider(settings: Settings | None = None) -> EmbeddingProvider:
    cfg = settings or get_settings()
    provider = cfg.embedding_provider.lower()
    if provider == "openai" or (provider == "auto" and cfg.openai_api_key):
        return OpenAIEmbeddingProvider(cfg)
    return DeterministicEmbeddingProvider(dimension=cfg.embedding_dimension)

"""Semantic cache: embedding query + TTL + corpus_version."""

from __future__ import annotations

import json
import logging
import math
import uuid
from typing import Any

from app.core.config import settings
from app.core.redis import get_redis

logger = logging.getLogger(__name__)

_INDEX_KEY = "semantic_cache:index:{version}:{scope}"
_ENTRY_KEY = "semantic_cache:entry:{version}:{scope}:{entry_id}"


def get_cached_answer(query: str, *, scope: str | None = None) -> dict | None:
    """
    Lookup semantic: so cosine embedding với các entry cùng corpus_version + scope.
    Hit nếu similarity >= threshold và TTL còn (Redis EXPIRE).
    """
    client = get_redis()
    if client is None:
        return None

    scope_key = _normalize_scope(scope)
    try:
        query_embedding = _embed_query(query)
        index_key = _INDEX_KEY.format(
            version=settings.corpus_version,
            scope=scope_key,
        )
        entry_ids = client.smembers(index_key)
        best: tuple[float, dict] | None = None

        for entry_id in entry_ids:
            entry_key = _ENTRY_KEY.format(
                version=settings.corpus_version,
                scope=scope_key,
                entry_id=entry_id,
            )
            raw = client.get(entry_key)
            if not raw:
                client.srem(index_key, entry_id)
                continue
            payload = json.loads(raw)
            stored_embedding = payload.get("embedding") or []
            score = _cosine_similarity(query_embedding, stored_embedding)
            if score < settings.cache_similarity_threshold:
                continue
            if best is None or score > best[0]:
                best = (
                    score,
                    {
                        "answer": payload["answer"],
                        "query": payload.get("query", query),
                        "sources": payload.get("sources") or [],
                    },
                )

        if best is None:
            return None
        logger.info(
            "Semantic cache hit score=%.4f version=%s scope=%s",
            best[0],
            settings.corpus_version,
            scope_key,
        )
        return best[1]
    except Exception as exc:  # noqa: BLE001
        logger.warning("Semantic cache get failed: %s", exc)
        return None


def set_cached_answer(
    query: str,
    result: dict,
    *,
    scope: str | None = None,
) -> None:
    """Lưu answer + embedding + sources với TTL."""
    client = get_redis()
    if client is None:
        return

    scope_key = _normalize_scope(scope)
    try:
        embedding = _embed_query(query)
        entry_id = uuid.uuid4().hex
        entry_key = _ENTRY_KEY.format(
            version=settings.corpus_version,
            scope=scope_key,
            entry_id=entry_id,
        )
        index_key = _INDEX_KEY.format(
            version=settings.corpus_version,
            scope=scope_key,
        )
        payload = {
            "query": query,
            "answer": result.get("answer", ""),
            "sources": result.get("sources") or [],
            "embedding": embedding,
            "corpus_version": settings.corpus_version,
            "scope": scope_key,
        }
        pipe = client.pipeline()
        pipe.set(
            entry_key,
            json.dumps(payload, ensure_ascii=False),
            ex=settings.cache_ttl_seconds,
        )
        pipe.sadd(index_key, entry_id)
        pipe.expire(index_key, settings.cache_ttl_seconds)
        pipe.execute()
        logger.info(
            "Semantic cache set version=%s scope=%s ttl=%s",
            settings.corpus_version,
            scope_key,
            settings.cache_ttl_seconds,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Semantic cache set failed: %s", exc)


def _embed_query(query: str) -> list[float]:
    from app.services.llm.client import get_embeddings

    vector = get_embeddings().embed_query(query)
    return [float(x) for x in vector]


def _normalize_scope(scope: str | None) -> str:
    return (scope or "default").strip().lower() or "default"


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)

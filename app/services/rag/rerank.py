"""Cross-encoder rerank: chấm lại candidates sau Chroma similarity search."""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

from langchain_core.documents import Document

from app.core.config import settings

logger = logging.getLogger(__name__)


@lru_cache
def get_cross_encoder() -> Any | None:
    """Lazy-load CrossEncoder; None nếu tắt / thiếu deps / lỗi load."""
    if not settings.rerank_enabled:
        return None
    try:
        from sentence_transformers import CrossEncoder
    except ImportError:
        logger.warning(
            "Package sentence-transformers chưa cài — bỏ qua rerank "
            "(uv sync / pip install sentence-transformers)",
        )
        return None

    try:
        model = CrossEncoder(settings.rerank_model)
        logger.info("Loaded rerank model=%s", settings.rerank_model)
        return model
    except Exception as exc:  # noqa: BLE001
        logger.warning("Không load được rerank model (%s) — bỏ qua rerank", exc)
        return None


def reset_cross_encoder() -> None:
    """Xóa cache model (test / đổi RERANK_MODEL)."""
    get_cross_encoder.cache_clear()


def rerank_documents(
    query: str,
    documents: list[Document],
    *,
    top_n: int | None = None,
) -> list[Document]:
    """
    Chấm relevance (query, chunk) bằng cross-encoder, sort desc, cắt top_n.
    Nếu model không sẵn sàng: trả documents[:top_n] (giữ thứ tự retrieve).
    """
    n = top_n if top_n is not None else settings.rerank_top_n
    if not documents:
        return []
    if n <= 0:
        return []

    model = get_cross_encoder()
    if model is None:
        return documents[:n]

    pairs = [(query, doc.page_content) for doc in documents]
    try:
        scores = model.predict(pairs)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Rerank predict failed (%s) — giữ thứ tự retrieve", exc)
        return documents[:n]

    ranked = sorted(
        zip(scores, documents, strict=True),
        key=lambda item: float(item[0]),
        reverse=True,
    )
    top = [doc for _, doc in ranked[:n]]
    if ranked:
        logger.info(
            "Reranked %s → %s (best_score=%.4f model=%s)",
            len(documents),
            len(top),
            float(ranked[0][0]),
            settings.rerank_model,
        )
    return top

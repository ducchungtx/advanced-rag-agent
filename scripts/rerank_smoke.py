"""
Smoke-test rerank: so thứ tự chunk trước/sau cross-encoder.

Chạy:
  uv run python -u scripts/rerank_smoke.py
  # hoặc: .venv/bin/python -u scripts/rerank_smoke.py
"""

from __future__ import annotations

from app.core.config import settings
from app.services.rag.retriever import retrieve_documents
from app.services.rag.rerank import rerank_documents
from app.services.rag.vectorstore import get_vectorstore


def _preview(text: str, n: int = 120) -> str:
    one = " ".join(text.split())
    return one if len(one) <= n else one[: n - 1] + "…"


def main() -> None:
    query = "Thời hạn giải quyết thủ tục thu hồi đất bồi thường là bao lâu?"
    fetch_k = settings.retrieve_k
    top_n = settings.rerank_top_n

    print(f"query={query!r}")
    print(f"retrieve_k={fetch_k} rerank_top_n={top_n} model={settings.rerank_model}")
    print(f"rerank_enabled={settings.rerank_enabled}")

    store = get_vectorstore()
    raw = store.similarity_search(query, k=fetch_k)
    print(f"\n=== BEFORE rerank (Chroma top {len(raw)}) ===")
    for i, doc in enumerate(raw, 1):
        src = doc.metadata.get("filename") or doc.metadata.get("source") or "?"
        print(f"{i:2d}. [{src}] {_preview(doc.page_content)}")

    ranked = rerank_documents(query, raw, top_n=top_n)
    print(f"\n=== AFTER rerank (top {len(ranked)}) ===")
    for i, doc in enumerate(ranked, 1):
        src = doc.metadata.get("filename") or doc.metadata.get("source") or "?"
        print(f"{i:2d}. [{src}] {_preview(doc.page_content)}")

    # Đường production (retrieve_documents đã gắn rerank)
    via_api = retrieve_documents(query)
    print(f"\nretrieve_documents() returned {len(via_api)} docs (expects {top_n} when enabled)")

    before_ids = [id(d) for d in raw[:top_n]]
    after_ids = [id(d) for d in ranked]
    if before_ids != after_ids:
        print("ORDER_CHANGED=yes (rerank đã đổi thứ tự so với Chroma top-n)")
    else:
        print("ORDER_CHANGED=no (thứ tự top-n trùng Chroma — vẫn có thể hợp lệ)")


if __name__ == "__main__":
    main()

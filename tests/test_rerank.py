"""Unit tests cho cross-encoder rerank (mock model — không tải HuggingFace)."""

from langchain_core.documents import Document

from app.services.rag import rerank as rerank_mod


class _FakeCrossEncoder:
    """Scores = độ dài page_content — dễ đoán thứ tự sau sort."""

    def predict(self, pairs: list[tuple[str, str]]) -> list[float]:
        return [float(len(text)) for _, text in pairs]


def test_rerank_documents_sorts_by_score_and_cuts_top_n(monkeypatch):
    monkeypatch.setattr(rerank_mod, "get_cross_encoder", lambda: _FakeCrossEncoder())

    docs = [
        Document(page_content="aa", metadata={"id": "short"}),
        Document(page_content="abcdefghij", metadata={"id": "long"}),
        Document(page_content="bbbb", metadata={"id": "mid"}),
    ]
    out = rerank_mod.rerank_documents("query", docs, top_n=2)
    assert [d.metadata["id"] for d in out] == ["long", "mid"]


def test_rerank_documents_degrades_when_model_missing(monkeypatch):
    monkeypatch.setattr(rerank_mod, "get_cross_encoder", lambda: None)
    docs = [
        Document(page_content="first"),
        Document(page_content="second"),
        Document(page_content="third"),
    ]
    out = rerank_mod.rerank_documents("q", docs, top_n=2)
    assert [d.page_content for d in out] == ["first", "second"]


def test_retrieve_documents_calls_rerank_when_enabled(monkeypatch):
    from app.services.rag import retriever as retriever_mod

    class _FakeStore:
        def similarity_search(self, query: str, k: int, filter=None):  # noqa: A002
            assert k == 20
            return [
                Document(page_content="c1"),
                Document(page_content="c2"),
                Document(page_content="c3"),
            ]

    monkeypatch.setattr(retriever_mod, "get_vectorstore", lambda: _FakeStore())
    monkeypatch.setattr(retriever_mod.settings, "rerank_enabled", True)
    monkeypatch.setattr(retriever_mod.settings, "retrieve_k", 20)
    monkeypatch.setattr(retriever_mod.settings, "rerank_top_n", 2)

    called: dict = {}

    def fake_rerank(query, documents, *, top_n=None):
        called["n"] = len(documents)
        called["top_n"] = top_n
        return documents[: top_n or 2]

    monkeypatch.setattr(
        "app.services.rag.rerank.rerank_documents",
        fake_rerank,
    )

    out = retriever_mod.retrieve_documents("hỏi luật đất")
    assert called["n"] == 3
    assert called["top_n"] == 2
    assert len(out) == 2

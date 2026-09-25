from langchain_core.documents import Document

from app.core.config import settings
from app.services.rag.vectorstore import get_vectorstore


def retrieve_documents(
    query: str,
    k: int | None = None,
    *,
    where: dict | None = None,
    rerank: bool | None = None,
) -> list[Document]:
    """
    Similarity search rồi (tuỳ chọn) cross-encoder rerank.
    `where` là metadata pre-filter Chroma (RBAC) — apply tại lúc search.
    """
    use_rerank = settings.rerank_enabled if rerank is None else rerank
    if k is not None:
        fetch_k = k
    elif use_rerank:
        fetch_k = settings.retrieve_k
    else:
        fetch_k = settings.top_k

    store = get_vectorstore()
    if where:
        docs = store.similarity_search(query, k=fetch_k, filter=where)
    else:
        docs = store.similarity_search(query, k=fetch_k)

    if not use_rerank:
        return docs

    from app.services.rag.rerank import rerank_documents

    return rerank_documents(query, docs, top_n=settings.rerank_top_n)

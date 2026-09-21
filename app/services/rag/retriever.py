from langchain_core.documents import Document

from app.core.config import settings
from app.services.rag.vectorstore import get_vectorstore


def retrieve_documents(
    query: str,
    k: int | None = None,
    *,
    where: dict | None = None,
) -> list[Document]:
    """
    Similarity search top-k.
    `where` là metadata pre-filter Chroma (RBAC) — apply tại lúc search.
    """
    top_k = k if k is not None else settings.top_k
    store = get_vectorstore()
    if where:
        return store.similarity_search(query, k=top_k, filter=where)
    return store.similarity_search(query, k=top_k)

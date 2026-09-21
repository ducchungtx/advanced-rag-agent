from langchain_core.documents import Document

from app.core.config import settings
from app.services.rag.vectorstore import get_vectorstore


def retrieve_documents(query: str, k: int | None = None) -> list[Document]:
    top_k = k if k is not None else settings.top_k
    retriever = get_vectorstore().as_retriever(search_kwargs={"k": top_k})
    return retriever.invoke(query)

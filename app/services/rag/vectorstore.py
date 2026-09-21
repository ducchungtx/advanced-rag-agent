from functools import lru_cache

from langchain_chroma import Chroma

from app.core.config import settings
from app.services.llm.client import get_embeddings


@lru_cache
def get_vectorstore() -> Chroma:
    return Chroma(
        persist_directory=settings.chroma_persist_dir,
        embedding_function=get_embeddings(),
    )

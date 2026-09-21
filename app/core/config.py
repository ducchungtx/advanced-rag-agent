from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # App
    app_name: str = "Advanced RAG Agent"
    app_env: str = "development"
    app_host: str = "127.0.0.1"
    app_port: int = 8000

    # Google Gemini
    google_api_key: str = ""
    google_model: str = "gemini-2.0-flash"
    embedding_model: str = "models/gemini-embedding-001"

    # Vector store
    vector_store: str = "chroma"
    chroma_persist_dir: str = "./data/chroma"
    chroma_host: str = "localhost"
    chroma_port: int = 8001

    # Redis (memory / cache — phase 2)
    redis_url: str = "redis://localhost:6379/0"

    # RAG — chunk ~1000 ổn cho VBPL nếu separators theo Điều/Khoản
    chunk_size: int = 1000
    chunk_overlap: int = 200
    top_k: int = 4
    data_dir: str = "./data/pdfs"  # hỗ trợ .pdf và .docx

    # LLM behavior
    temperature: float = 0.0


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

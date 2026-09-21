from fastapi import FastAPI

from app.api import api_router
from app.core.config import settings


def create_app() -> FastAPI:
    application = FastAPI(
        title=settings.app_name,
        description="Chat agent AI với Advanced RAG (retrieve → reason → answer).",
        version="0.1.0",
    )
    application.include_router(api_router)
    return application


app = create_app()

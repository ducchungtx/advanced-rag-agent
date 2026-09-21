"""
Legacy entrypoint — chuyển sang:

  uvicorn app.main:app --reload

Giữ file này để tương thích tạm thời.
"""

from app.main import app

__all__ = ["app"]

if __name__ == "__main__":
    import uvicorn

    from app.core.config import settings

    uvicorn.run(
        "app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.app_env == "development",
    )

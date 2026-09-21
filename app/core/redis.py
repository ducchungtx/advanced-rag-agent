"""Redis client cho semantic cache (phase 2)."""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)


@lru_cache
def get_redis() -> Any | None:
    """
    Trả Redis client hoặc None nếu không kết nối được.
    Cache layer phải degrade thành miss, không làm sập API.
    """
    try:
        import redis
    except ImportError:
        logger.warning("Package redis chưa cài — semantic cache tắt")
        return None

    client = redis.Redis.from_url(
        settings.redis_url,
        decode_responses=True,
        socket_connect_timeout=1.5,
        socket_timeout=2.0,
    )
    try:
        client.ping()
    except Exception as exc:  # noqa: BLE001 — degrade gracefully
        logger.warning("Redis không sẵn sàng (%s) — semantic cache tắt", exc)
        return None
    return client


def reset_redis_client() -> None:
    """Xóa cache client (dùng khi đổi REDIS_URL trong test)."""
    get_redis.cache_clear()

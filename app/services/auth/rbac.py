"""RBAC: role → Chroma metadata where filter."""

from __future__ import annotations

from typing import Any

# citizen mặc định chỉ thấy tài liệu công khai.
ROLE_TO_AUDIENCE: dict[str, list[str]] = {
    "citizen": ["public"],
    "staff": ["public", "internal"],
    "legal_staff": ["public", "internal", "legal_staff"],
}

DEFAULT_ROLE = "citizen"


def normalize_role(role: str | None) -> str:
    value = (role or DEFAULT_ROLE).strip().lower()
    if value not in ROLE_TO_AUDIENCE:
        return DEFAULT_ROLE
    return value


def role_to_where(role: str | None) -> dict[str, Any]:
    """
    Map role → filter Chroma `where`.
    Retriever chỉ apply; không hard-code role trong vector query builder.
    """
    audiences = ROLE_TO_AUDIENCE[normalize_role(role)]
    return {"audience": {"$in": audiences}}

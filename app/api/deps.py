"""API dependency helpers."""

from __future__ import annotations

from typing import Annotated

from fastapi import Header
from pydantic import BaseModel, Field

from app.services.auth.rbac import DEFAULT_ROLE, normalize_role


class UserContext(BaseModel):
    """Identity mỏng từ header — deps biết *ai*, rbac biết *filter gì*."""

    role: str = Field(default=DEFAULT_ROLE)


def get_user_context(
    x_user_role: Annotated[
        str | None,
        Header(
            description="Vai trò RBAC: citizen | staff | legal_staff (mặc định citizen)",
        ),
    ] = None,
) -> UserContext:
    return UserContext(role=normalize_role(x_user_role))

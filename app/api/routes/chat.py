from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import UserContext, get_user_context
from app.models.schemas import ChatRequest, ChatResponse
from app.services.agent.react import run_agent
from app.services.auth.rbac import role_to_where

router = APIRouter()


@router.post("", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    user: UserContext = Depends(get_user_context),
) -> ChatResponse:
    try:
        where = role_to_where(user.role)
        result = run_agent(
            request.query,
            where=where,
            role=user.role,
        )
        return ChatResponse(**result)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

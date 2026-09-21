from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Câu hỏi của người dùng")
    session_id: str | None = Field(
        default=None,
        description="ID phiên chat (dùng cho memory — phase 2)",
    )


class ChatResponse(BaseModel):
    answer: str
    query: str
    sources: list[str] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: str
    version: str

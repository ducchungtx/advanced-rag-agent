"""ReAct agent — vòng lặp thủ công + Gemini Function Calling."""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from app.services.agent.tools import execute_tool, get_langchain_tools
from app.services.llm.client import get_llm
from app.services.llm.prompts import AGENT_SYSTEM_PROMPT

logger = logging.getLogger(__name__)

DEFAULT_MAX_ITERATIONS = 5


def run_agent(
    query: str,
    *,
    where: dict[str, Any] | None = None,
    role: str | None = None,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    use_cache: bool = True,
) -> dict:
    """
    ReAct: LLM → tool calls → execute_tool (Observation) → lặp.
    Cache semantic (nếu bật) bọc ngoài vòng lặp.
    """
    if use_cache:
        from app.services.cache.semantic import get_cached_answer, set_cached_answer

        cached = get_cached_answer(query, scope=role)
        if cached is not None:
            logger.info("Semantic cache hit for query (scope=%s)", role)
            return cached

    result = _react_loop(
        query,
        where=where,
        max_iterations=max_iterations,
    )

    if use_cache:
        from app.services.cache.semantic import set_cached_answer

        set_cached_answer(query, result, scope=role)

    return result


def _react_loop(
    query: str,
    *,
    where: dict[str, Any] | None = None,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
) -> dict:
    llm = get_llm().bind_tools(get_langchain_tools())
    messages: list = [
        SystemMessage(content=AGENT_SYSTEM_PROMPT),
        HumanMessage(content=query),
    ]
    sources: list[str] = []

    final_text = ""
    for step in range(max_iterations):
        ai_msg = llm.invoke(messages)
        if not isinstance(ai_msg, AIMessage):
            ai_msg = AIMessage(content=str(ai_msg))
        messages.append(ai_msg)

        tool_calls = getattr(ai_msg, "tool_calls", None) or []
        if not tool_calls:
            final_text = _message_text(ai_msg)
            break

        logger.info(
            "ReAct step %s: %s",
            step + 1,
            [tc.get("name") for tc in tool_calls],
        )
        for tool_call in tool_calls:
            name = tool_call.get("name") or ""
            args = tool_call.get("args") or {}
            tool_call_id = tool_call.get("id") or f"call_{step}_{name}"
            observation = execute_tool(
                name,
                where=where,
                sources_out=sources,
                **args,
            )
            messages.append(
                ToolMessage(content=observation, tool_call_id=tool_call_id)
            )
    else:
        # Hết số bước mà model vẫn gọi tool — xin câu trả lời cuối không tool.
        logger.warning("ReAct đạt max_iterations=%s — buộc final answer", max_iterations)
        wrap_up = get_llm().invoke(
            messages
            + [
                HumanMessage(
                    content=(
                        "Bạn đã hết số bước dùng tool. "
                        "Hãy trả lời cuối cùng dựa trên Observation hiện có."
                    )
                )
            ]
        )
        final_text = _message_text(wrap_up)

    if not final_text.strip():
        final_text = (
            "Xin lỗi, tôi chưa đủ thông tin để trả lời. "
            "Bạn có thể diễn đạt lại câu hỏi."
        )

    return {
        "answer": final_text,
        "query": query,
        "sources": sources,
    }


def _message_text(message: Any) -> str:
    """Chuẩn hóa content AIMessage (str hoặc list block) thành str."""
    text_attr = getattr(message, "text", None)
    if isinstance(text_attr, str) and text_attr.strip():
        return text_attr

    content = getattr(message, "content", message)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                if block.get("type") == "text":
                    parts.append(str(block.get("text", "")))
                elif "text" in block:
                    parts.append(str(block["text"]))
            else:
                text = getattr(block, "text", None)
                if text:
                    parts.append(str(text))
        return "".join(parts)
    return str(content)

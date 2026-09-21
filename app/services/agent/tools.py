"""Định nghĩa tools cho Function Calling / ReAct (phase 2)."""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any, Callable

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

RAG_SEARCH_DESCRIPTION = (
    "Tra cứu kiến thức nội bộ về quy định đất đai Việt Nam từ kho tài liệu "
    "đã index (Luật Đất đai, nghị định, thông tư, văn bản hướng dẫn). "
    "Dùng khi người dùng hỏi về: quyền sử dụng đất, thu hồi/bồi thường, "
    "chuyển mục đích, cấp giấy chứng nhận, quy hoạch/kế hoạch sử dụng đất, "
    "nghĩa vụ tài chính về đất, thủ tục hành chính đất đai, hoặc cần trích dẫn "
    "điều/khoản từ văn bản pháp luật nội bộ. "
    "KHÔNG dùng cho: tỷ giá ngoại tệ, giá vàng, lãi suất, dữ liệu thị trường "
    "theo thời gian thực, tin tức thời sự, hay bất kỳ thông tin cần gọi API "
    "ngoại vi — với các câu hỏi đó hãy dùng tool tương ứng "
    "(ví dụ get_exchange_rate). "
    "Tham số query: viết lại thành câu hỏi pháp lý ngắn gọn bằng tiếng Việt, "
    "ưu tiên giữ thuật ngữ chuyên ngành (Điều, Khoản, loại đất, thủ tục...)."
)

EXCHANGE_RATE_DESCRIPTION = (
    "Lấy tỷ giá ngoại tệ hiện tại từ API bên ngoài (ví dụ USD/VND, EUR/VND). "
    "Dùng khi người dùng hỏi tỷ giá, quy đổi tiền tệ, hoặc cần số liệu thị trường "
    "theo thời gian thực. "
    "KHÔNG dùng cho quy định pháp luật, thủ tục đất đai, hay nội dung trong "
    "kho tài liệu nội bộ — các câu hỏi đó dùng rag_search."
)

# API công khai, không cần key; hỗ trợ VND (khác Frankfurter/ECB).
EXCHANGE_RATE_API_URL = "https://open.er-api.com/v6/latest/{base}"
EXCHANGE_RATE_TIMEOUT_SECONDS = 10


class RagSearchInput(BaseModel):
    query: str = Field(..., description="Câu hỏi pháp lý ngắn gọn bằng tiếng Việt")


class ExchangeRateInput(BaseModel):
    base: str = Field(default="USD", description="Mã tiền tệ gốc, ví dụ USD")
    quote: str = Field(default="VND", description="Mã tiền tệ đích, ví dụ VND")


def get_available_tools() -> list[dict]:
    """Danh sách tool metadata — gắn vào LLM tool-calling."""
    return [
        {
            "name": "rag_search",
            "description": RAG_SEARCH_DESCRIPTION,
            "parameters": {"query": "str"},
        },
        {
            "name": "get_exchange_rate",
            "description": EXCHANGE_RATE_DESCRIPTION,
            "parameters": {"base": "str", "quote": "str"},
        },
    ]


def get_langchain_tools() -> list[StructuredTool]:
    """Schema tools cho model.bind_tools — thực thi thật qua execute_tool."""

    def _rag_search_stub(query: str) -> str:
        return ""

    def _exchange_rate_stub(base: str = "USD", quote: str = "VND") -> str:
        return ""

    return [
        StructuredTool.from_function(
            func=_rag_search_stub,
            name="rag_search",
            description=RAG_SEARCH_DESCRIPTION,
            args_schema=RagSearchInput,
        ),
        StructuredTool.from_function(
            func=_exchange_rate_stub,
            name="get_exchange_rate",
            description=EXCHANGE_RATE_DESCRIPTION,
            args_schema=ExchangeRateInput,
        ),
    ]


def format_tool_error_observation(
    tool_name: str,
    error: BaseException,
    *,
    error_type: str | None = None,
) -> str:
    """
    Đóng gói lỗi tool thành Observation cho ReAct.

    Gemini đọc chuỗi này như kết quả tool (không phải exception HTTP).
    Giữ ngắn, có mã lỗi máy đọc được, và gợi ý bước tiếp theo.
    """
    kind = error_type or type(error).__name__
    # Không dump traceback / secret vào Observation.
    detail = str(error).strip() or "unknown error"
    if len(detail) > 300:
        detail = detail[:297] + "..."

    return (
        f"[TOOL_ERROR] tool={tool_name} type={kind}\n"
        f"message={detail}\n"
        "hint=Tool thất bại. Đừng crash; hãy thử tool khác, rút gọn tham số, "
        "hoặc trả lời người dùng rằng dữ liệu tạm thời không lấy được và "
        "phần còn lại vẫn trả lời được từ kiến thức/tool khác."
    )


def execute_tool(
    tool_name: str,
    *,
    where: dict[str, Any] | None = None,
    sources_out: list[str] | None = None,
    **kwargs: Any,
) -> str:
    """
    Chạy tool an toàn: mọi exception → Observation string, không raise lên API.
    ReAct loop luôn nhận str để nhét vào bước Observation.
    """
    tool_map = build_tool_map(where=where, sources_out=sources_out)
    fn = tool_map.get(tool_name)
    if fn is None:
        return format_tool_error_observation(
            tool_name,
            ValueError(f"Unknown tool: {tool_name}"),
            error_type="UnknownTool",
        )

    try:
        result = fn(**kwargs)
        if result is None or (isinstance(result, str) and not result.strip()):
            return (
                f"[TOOL_EMPTY] tool={tool_name}\n"
                "message=Tool chạy OK nhưng không có dữ liệu.\n"
                "hint=Thử diễn đạt lại query hoặc dùng tool khác."
            )
        return str(result)
    except TimeoutError as exc:
        logger.warning("Tool %s timeout: %s", tool_name, exc)
        return format_tool_error_observation(tool_name, exc, error_type="Timeout")
    except ConnectionError as exc:
        logger.warning("Tool %s connection error: %s", tool_name, exc)
        return format_tool_error_observation(
            tool_name, exc, error_type="ConnectionError"
        )
    except Exception as exc:
        # Rate limit, HTTP 429/5xx từ client lib, NotImplemented, v.v.
        logger.exception("Tool %s failed", tool_name)
        type_name = type(exc).__name__
        lower = str(exc).lower()
        if "rate" in lower and "limit" in lower:
            type_name = "RateLimit"
        elif "timeout" in lower:
            type_name = "Timeout"
        return format_tool_error_observation(tool_name, exc, error_type=type_name)


def fetch_exchange_rate(base: str = "USD", quote: str = "VND") -> str:
    """Gọi API tỷ giá; raise ConnectionError/TimeoutError/ValueError khi lỗi."""
    base_code = (base or "USD").strip().upper()
    quote_code = (quote or "VND").strip().upper()
    url = EXCHANGE_RATE_API_URL.format(base=base_code)

    try:
        with urllib.request.urlopen(url, timeout=EXCHANGE_RATE_TIMEOUT_SECONDS) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except TimeoutError as exc:
        raise TimeoutError(f"Timeout khi gọi tỷ giá {base_code}/{quote_code}") from exc
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            raise RuntimeError(f"Rate limit tỷ giá HTTP {exc.code}") from exc
        raise ConnectionError(f"HTTP {exc.code} khi gọi tỷ giá") from exc
    except urllib.error.URLError as exc:
        raise ConnectionError(f"Không kết nối được API tỷ giá: {exc.reason}") from exc

    if payload.get("result") != "success":
        raise ValueError(f"API tỷ giá trả lỗi: {payload.get('result')}")

    rates = payload.get("rates") or {}
    rate = rates.get(quote_code)
    if rate is None:
        raise ValueError(f"Không có tỷ giá {base_code}/{quote_code}")

    updated = payload.get("time_last_update_utc") or payload.get("date") or "unknown"
    return f"1 {base_code} = {rate} {quote_code} (updated={updated})"


def build_tool_map(
    *,
    where: dict[str, Any] | None = None,
    sources_out: list[str] | None = None,
) -> dict[str, Callable]:
    """Map tên tool → hàm thực thi."""
    from app.services.rag.retriever import retrieve_documents

    def rag_search(query: str) -> str:
        docs = retrieve_documents(query, where=where)
        if sources_out is not None:
            for doc in docs:
                source = doc.metadata.get("source")
                if source and source not in sources_out:
                    sources_out.append(source)
        if not docs:
            return (
                "[TOOL_EMPTY] tool=rag_search\n"
                "message=Không tìm thấy đoạn văn bản phù hợp trong kho nội bộ.\n"
                "hint=Diễn đạt lại câu hỏi pháp lý hoặc bỏ bớt điều kiện."
            )
        return "\n\n".join(doc.page_content for doc in docs)

    def get_exchange_rate(base: str = "USD", quote: str = "VND") -> str:
        return fetch_exchange_rate(base=base, quote=quote)

    return {
        "rag_search": rag_search,
        "get_exchange_rate": get_exchange_rate,
    }

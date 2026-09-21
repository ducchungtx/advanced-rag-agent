"""Định nghĩa tools cho Function Calling / ReAct (phase 2)."""

from __future__ import annotations

import logging
from typing import Any, Callable

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


def get_available_tools() -> list[dict]:
    """Danh sách tool metadata — sẽ gắn vào LLM tool-calling."""
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


def execute_tool(tool_name: str, **kwargs: Any) -> str:
    """
    Chạy tool an toàn: mọi exception → Observation string, không raise lên API.
    ReAct loop luôn nhận str để nhét vào bước Observation.
    """
    tool_map = build_tool_map()
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


def build_tool_map() -> dict[str, Callable]:
    """Map tên tool → hàm thực thi (phase 2)."""
    from app.services.rag.retriever import retrieve_documents

    def rag_search(query: str) -> str:
        docs = retrieve_documents(query)
        return "\n\n".join(doc.page_content for doc in docs)

    def get_exchange_rate(base: str = "USD", quote: str = "VND") -> str:
        # Phase 2: gắn API ngoại vi thật.
        # Lỗi kết nối/timeout/rate-limit: raise tại đây;
        # execute_tool sẽ biến thành Observation, không sập API.
        raise NotImplementedError(
            f"get_exchange_rate({base}/{quote}) chưa được triển khai."
        )

    return {
        "rag_search": rag_search,
        "get_exchange_rate": get_exchange_rate,
    }

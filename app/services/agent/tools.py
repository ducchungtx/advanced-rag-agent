"""Định nghĩa tools cho Function Calling / ReAct (phase 2)."""

from typing import Callable


def get_available_tools() -> list[dict]:
    """Danh sách tool metadata — sẽ gắn vào LLM tool-calling."""
    return [
        {
            "name": "rag_search",
            "description": "Tìm kiếm tài liệu nội bộ liên quan đến câu hỏi.",
            "parameters": {"query": "str"},
        },
    ]


def build_tool_map() -> dict[str, Callable]:
    """Map tên tool → hàm thực thi (phase 2)."""
    from app.services.rag.retriever import retrieve_documents

    def rag_search(query: str) -> str:
        docs = retrieve_documents(query)
        return "\n\n".join(doc.page_content for doc in docs)

    return {"rag_search": rag_search}

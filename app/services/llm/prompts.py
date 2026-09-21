RAG_SYSTEM_PROMPT = """Bạn là trợ lý nội bộ. Chỉ trả lời dựa trên tài liệu được cung cấp.
Nếu không đủ thông tin trong tài liệu, hãy nói rõ là không tìm thấy."""


def build_rag_prompt(query: str, context: str) -> str:
    return (
        f"{RAG_SYSTEM_PROMPT}\n\n"
        f"Tài liệu:\n{context}\n\n"
        f"Câu hỏi: {query}"
    )

"""Smoke-test retrieve — không dùng tên app.py để tránh che package app/."""

from app.services.rag.retriever import retrieve_documents

if __name__ == "__main__":
    query = "Thời gian ăn trưa là lúc mấy giờ?"
    docs = retrieve_documents(query)
    print(f"Đã tìm thấy {len(docs)} đoạn tài liệu liên quan nhất!")
    for i, doc in enumerate(docs, 1):
        print(f"\n--- Đoạn {i} ---\n{doc.page_content}")

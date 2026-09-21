"""Smoke-test retrieve — không dùng tên app.py để tránh che package app/."""

from app.services.rag.retriever import retrieve_documents

if __name__ == "__main__":
    query = "Điều kiện chuyển nhượng quyền sử dụng đất theo Nghị định?"
    docs = retrieve_documents(query)
    print(f"FOUND={len(docs)}")
    for i, doc in enumerate(docs, 1):
        src = doc.metadata.get("filename", "?")
        preview = doc.page_content[:500].encode("utf-8", errors="replace").decode("utf-8")
        print(f"\n--- chunk {i} ({src}) ---\n{preview}")

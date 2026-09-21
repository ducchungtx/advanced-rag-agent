"""ReAct agent skeleton — sẽ mở rộng với LangGraph / tool-calling."""

from app.services.llm.client import get_llm
from app.services.llm.prompts import build_rag_prompt
from app.services.rag.retriever import retrieve_documents


def run_agent(query: str) -> dict:
    """
    Pipeline hiện tại: retrieve → prompt → LLM.
    Phase 2: thay bằng ReAct loop + tools (search, calculator, ...).
    """
    docs = retrieve_documents(query)
    context = "\n".join(doc.page_content for doc in docs)
    prompt = build_rag_prompt(query, context)
    response = get_llm().invoke(prompt)

    sources = []
    for doc in docs:
        source = doc.metadata.get("source")
        if source and source not in sources:
            sources.append(source)

    return {
        "answer": response.content,
        "query": query,
        "sources": sources,
    }

# Architecture — Advanced RAG Agent

## Tổng quan

```
Client ──► FastAPI (app/api)
              │
              ▼
         Agent (app/services/agent)
              │  retrieve + (phase 2: tools / ReAct)
              ▼
    ┌─────────┴─────────┐
    │ RAG               │ LLM
    │ ingest / retrieve │ Gemini + prompts
    │ ChromaDB          │ (+ reranker phase 3)
    └───────────────────┘
```

## Module map

| Thư mục | Trách nhiệm |
|---------|-------------|
| `app/api` | HTTP endpoints, không chứa business logic nặng |
| `app/core` | Settings từ `.env` (`pydantic-settings`) |
| `app/models` | Request/response schemas |
| `app/services/rag` | Load PDF/DOCX, chunk pháp lý (Điều/Khoản), Chroma, retrieve |
| `app/services/agent` | Orchestration: hiện tại RAG pipeline; sau này ReAct |
| `app/services/llm` | Khởi tạo Gemini / embeddings, prompt templates |
| `app/utils` | Helper dùng chung |
| `eval/` | Đánh giá Faithfulness / relevancy (Ragas) |
| `tests/` | Unit + API tests |

## Luồng `/chat` (phase 1)

1. `ChatRequest.query` vào `api/routes/chat.py`
2. `run_agent(query)` gọi `retrieve_documents`
3. Ghép context + `build_rag_prompt`
4. `get_llm().invoke(...)` → `ChatResponse`

## Data

- `data/pdfs/` — tài liệu nguồn `.pdf` / `.docx` (commit được nếu không nhạy cảm)
- `data/chroma/` — vector index (gitignore)

## Docker Compose

- **api**: uvicorn `app.main:app`
- **redis**: session / memory (phase 2)
- **chromadb**: vector DB server (phase 2 có thể chuyển từ local persist sang client HTTP)

## Ghi chú thiết kế

- Business logic nằm trong `services/`, API chỉ thin wrapper.
- Config tập trung ở `core/config.py` — không hard-code key trong code.
- Agent layer tách sớm để sau này gắn LangGraph / tool-calling không đụng API.

# Advanced RAG Agent

Chat agent AI hỗ trợ nội bộ: **retrieve → reason → answer** (Gemini + Chroma + ReAct tools).

## Cấu trúc

```
app/
├── api/          # FastAPI routers (+ deps RBAC)
├── core/         # Config, env, Redis client
├── models/       # Pydantic schemas
├── services/
│   ├── rag/      # Ingest, retrieve, Chroma
│   ├── agent/    # ReAct loop + tools
│   ├── cache/    # Semantic cache Redis
│   ├── auth/     # RBAC role → where
│   └── llm/      # Gemini client + prompts
└── utils/
data/             # tài liệu nguồn + chroma persist
eval/             # Ragas evaluation scaffold
tests/
docs/
├── architecture.md    # Tài liệu hệ thống + sơ đồ
├── learning-guide.md  # Tài liệu học tập / onboarding
└── notes.txt
```

Chi tiết hơn:
- [docs/architecture.md](docs/architecture.md) — tài liệu hệ thống + sơ đồ
- [docs/learning-guide.md](docs/learning-guide.md) — tài liệu học tập / onboarding

## Setup nhanh

```bash
# 1. Tạo venv + cài deps (khuyến nghị uv)
uv sync --all-extras

# 2. Cấu hình env
copy .env.example .env   # Windows
# điền GOOGLE_API_KEY; kiểm tra REDIS_URL, CORPUS_VERSION

# 3. Bật Redis (semantic cache) — cần Docker Desktop
docker compose up -d redis

# 4. Ingest PDF/DOCX/DOC (gắn metadata audience=public)
# Đặt file vào DATA_DIR (mặc định ./data/docs)
uv run python -c "from app.services.rag.ingest import ingest_directory; print(ingest_directory())"

# 5. Chạy API
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
# hoặc: make run
```

Swagger UI: http://127.0.0.1:8000/docs

### API chính

| Method | Path | Mô tả |
|--------|------|--------|
| GET | `/health` | Health check |
| POST | `/chat` | Hỏi đáp agent `{ "query": "..." }` + header tùy chọn `X-User-Role: citizen\|staff\|legal_staff` |

## Docker

```bash
docker compose up --build
```

Services: `api` (8000), `redis` (6379), `chromadb` (8001).

## Lộ trình

| Phase | Nội dung |
|-------|----------|
| 1 | RAG cơ bản: ingest PDF/DOCX/DOC → Chroma → Gemini |
| 2 (hiện tại) | ReAct + tools + Redis semantic cache + RBAC |
| 3 | Reranker + Ragas eval |

## Scripts tiện ích

- `main.py` — alias chạy uvicorn `app.main:app`
- `scripts/retrieve_smoke.py` — test nhanh retrieve
- `python -m eval.run_ragas` — scaffold đánh giá Ragas

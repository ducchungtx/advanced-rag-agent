# Advanced RAG Agent

Chat agent AI hỗ trợ nội bộ: **retrieve → reason → answer** (Gemini + Chroma), sẵn sàng mở rộng ReAct / tools.

## Cấu trúc

```
app/
├── api/          # FastAPI routers
├── core/         # Config, env
├── models/       # Pydantic schemas
├── services/
│   ├── rag/      # Ingest, retrieve, Chroma
│   ├── agent/    # ReAct loop + tools (skeleton)
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
uv venv
uv pip install -e ".[dev]"

# hoặc: python -m venv .venv && pip install -e ".[dev]"

# 2. Cấu hình env
copy .env.example .env   # Windows
# điền GOOGLE_API_KEY

# 3. Ingest PDF/DOCX (nếu chưa có data/chroma)
# Đặt file vào DATA_DIR (mặc định ./data/pdfs), hỗ trợ .pdf và .docx
python -c "from app.services.rag.ingest import ingest_directory; print(ingest_directory())"
# Hoặc một file: ingest_file("path/to/van-ban.docx")

# 4. Chạy API
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Swagger UI: http://127.0.0.1:8000/docs

### API chính

| Method | Path | Mô tả |
|--------|------|--------|
| GET | `/health` | Health check |
| POST | `/chat` | Hỏi đáp RAG `{ "query": "..." }` |

## Docker

```bash
docker compose up --build
```

Services: `api` (8000), `redis` (6379), `chromadb` (8001).

## Lộ trình

| Phase | Nội dung |
|-------|----------|
| 1 (hiện tại) | RAG cơ bản: ingest PDF/DOCX → Chroma → Gemini |
| 2 | ReAct agent + tools + Redis memory |
| 3 | Reranker + Ragas eval |

## Scripts tiện ích

- `main.py` — alias chạy uvicorn `app.main:app`
- `scripts/retrieve_smoke.py` — test nhanh retrieve
- `python -m eval.run_ragas` — scaffold đánh giá Ragas

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

### Windows

```bash
# 1. Tạo venv + cài deps (khuyến nghị uv) — pywin32 được cài tự động
uv sync --all-extras

# 2. Cấu hình env
copy .env.example .env
# điền GOOGLE_API_KEY; kiểm tra REDIS_URL, CORPUS_VERSION

# 3. Bật Redis (semantic cache) — cần Docker Desktop
docker compose up -d redis

# 4. Ingest PDF/DOCX/DOC — .doc cần Microsoft Word (COM) đã cài
# Đặt file vào DATA_DIR (mặc định ./data/docs)
make ingest
# hoặc: uv run python -u scripts/run_ingest.py

# 5. Chạy API
make run
```

### macOS / Linux

```bash
# 1. Tạo venv + cài deps
uv sync --all-extras

# 2. Cấu hình env
cp .env.example .env
# điền GOOGLE_API_KEY; kiểm tra REDIS_URL, CORPUS_VERSION

# 3. LibreOffice — bắt buộc nếu ingest file .doc (Word 97–2003)
# macOS: brew install --cask libreoffice
# Linux: apt/yum install libreoffice (đảm bảo `soffice` có trên PATH)

# 4. Bật Redis
docker compose up -d redis

# 5. Ingest + chạy API
make ingest
make run
```

**Đọc `.doc` theo môi trường:** Windows ưu tiên Word COM (`pywin32`); macOS/Linux (và Windows không có Word) dùng LibreOffice headless (`soffice`).

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

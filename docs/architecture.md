# Kiến trúc hệ thống — Advanced RAG Agent (Đất đai)

> Tài liệu kỹ thuật cho vận hành / phát triển.  
> Mục tiêu sản phẩm: agent trả lời kiến thức **quy định đất đai** dựa trên kho văn bản nội bộ, sẵn sàng mở rộng ReAct + tool ngoại vi.

**Trạng thái:** Phase 1 runtime đã chạy; Phase 2 (ReAct loop đầy đủ, Redis semantic cache, RBAC) đang scaffold / thiết kế.

---

## 1. Tổng quan hệ thống

Hệ thống là API FastAPI nhận câu hỏi, retrieve ngữ cảnh từ Chroma (đã ingest văn bản pháp luật), rồi sinh câu trả lời bằng Gemini.

```mermaid
flowchart TB
    subgraph Client
        U[Người dùng / Client HTTP]
    end

    subgraph API["app/api — Transport"]
        H[GET /health]
        C[POST /chat]
    end

    subgraph Agent["app/services/agent — Orchestration"]
        RA[run_agent]
        Tools["tools.py<br/>rag_search · get_exchange_rate<br/>execute_tool"]
    end

    subgraph RAG["app/services/rag"]
        IN[ingest PDF/DOCX/DOC]
        VS[vectorstore Chroma]
        RT[retriever top-k]
    end

    subgraph LLM["app/services/llm"]
        EMB[Embeddings Gemini]
        GEN[LLM Gemini]
        PR[prompts]
    end

    subgraph Data["Lưu trữ"]
        DOC[(data/docs<br/>nguồn VBPL)]
        CH[(data/chroma<br/>vector index)]
        RD[(Redis — phase 2)]
    end

    U --> H & C
    C --> RA
    RA --> RT
    RA --> PR --> GEN
    RT --> VS --> CH
    IN --> DOC
    IN --> EMB --> CH
    Tools -.->|scaffold| RA
    RD -.->|semantic cache / memory| RA
```

| Thành phần | Vai trò | Trạng thái |
|------------|---------|------------|
| FastAPI (`/health`, `/chat`) | HTTP, thin wrapper | ✅ |
| Agent `run_agent` | Orchestrate retrieve → prompt → LLM | ✅ (pipeline thẳng) |
| RAG ingest | Load, chunk pháp lý, embed, persist Chroma | ✅ |
| RAG retrieve | Similarity search top-k | ✅ |
| Gemini LLM + embeddings | Sinh câu trả lời / vector | ✅ |
| Tools + `execute_tool` | Metadata tool + Observation an toàn khi lỗi | ✅ scaffold |
| ReAct loop đầy đủ | Thought → Action → Observation lặp | 🔲 phase 2 |
| Redis semantic cache | Cache câu hỏi tương tự | 🔲 thiết kế |
| RBAC metadata filter | Pre-filter theo role | 🔲 thiết kế |

---

## 2. Cấu trúc thư mục & Separation of Concerns

```mermaid
flowchart LR
    subgraph api["api/"]
        routes[routes]
        deps[deps]
    end
    subgraph core["core/"]
        cfg[config.py]
    end
    subgraph models["models/"]
        sch[schemas]
    end
    subgraph services["services/"]
        rag[rag/]
        agent[agent/]
        llm[llm/]
    end

    routes -->|gọi| agent
    agent -->|retrieve| rag
    agent -->|prompt + invoke| llm
    rag --> cfg
    llm --> cfg
    routes --> sch
```

| Thư mục | Trách nhiệm | Không làm |
|---------|-------------|-----------|
| `app/api` | HTTP, validate request/response | Business RAG / LLM |
| `app/core` | Settings từ `.env` | Logic nghiệp vụ |
| `app/models` | Pydantic schemas | I/O DB / LLM |
| `app/services/rag` | Ingest, chunk, Chroma, retrieve | Chọn tool / HTTP |
| `app/services/agent` | Orchestration, tool metadata, an toàn tool | Chi tiết embedding |
| `app/services/llm` | Client Gemini, prompts | Routing HTTP |
| `eval/` | Ragas scaffold | Runtime API |
| `data/docs` | Tài liệu nguồn | — |
| `data/chroma` | Index vector (gitignore) | — |

**Vị trí thiết kế (chưa code đầy đủ) — SoC đã chốt:**

| Concern | Đặt tại |
|---------|---------|
| Semantic Cache (Redis) | `services/cache/semantic.py` + `core/redis.py` |
| RBAC → metadata filter | `services/auth/rbac.py`; identity ở `api/deps.py` |
| Apply `where` lúc retrieve | `services/rag/retriever.py` (nhận filter, không biết role) |

---

## 3. Pipeline ingest (đã triển khai)

Nguồn: `.pdf` / `.docx` / `.doc` (Windows COM cho `.doc`) → chunk theo cấu trúc pháp lý → embedding → Chroma.

```mermaid
flowchart LR
    A[Thư mục DATA_DIR<br/>data/docs] --> B{Phần mở rộng}
    B -->|.pdf| C1[PyPDFLoader]
    B -->|.docx| C2[Docx2txtLoader]
    B -->|.doc| C3[LegacyDocLoader<br/>Word COM]
    C1 & C2 & C3 --> D[Document + metadata<br/>source, filename, filetype]
    D --> E[RecursiveCharacterTextSplitter<br/>LEGAL_SEPARATORS]
    E --> F[Gemini Embeddings]
    F --> G[(Chroma<br/>data/chroma)]
```

**API ingest chính:**

| Hàm | Mô tả |
|-----|--------|
| `ingest_file(path)` | Một file theo suffix |
| `ingest_directory(dir?)` | Đệ quy PDF + DOCX + DOC |
| `get_legal_text_splitter()` | Separators: Chương → Mục → Điều → Khoản → điểm |

**Tham số mặc định:** `chunk_size=1000`, `chunk_overlap=200` (`app/core/config.py`).

---

## 4. Luồng runtime `/chat` (Phase 1 — đang chạy)

```mermaid
sequenceDiagram
    participant Client
    participant Chat as api/routes/chat.py
    participant Agent as agent/react.run_agent
    participant Ret as rag/retriever
    participant Chroma as data/chroma
    participant LLM as llm/client Gemini

    Client->>Chat: POST /chat { query }
    Chat->>Agent: run_agent(query)
    Agent->>Ret: retrieve_documents(query)
    Ret->>Chroma: similarity search top_k
    Chroma-->>Ret: Documents
    Ret-->>Agent: docs
    Agent->>LLM: build_rag_prompt + invoke
    LLM-->>Agent: answer
    Agent-->>Chat: { answer, query, sources }
    Chat-->>Client: ChatResponse
```

**Lưu ý:** Phase 1 gọi retrieve trực tiếp trong `run_agent`, chưa qua ReAct / Function Calling. Tool `rag_search` đã khai báo để phase 2 gắn vào loop.

---

## 5. Agent Tools & an toàn Observation (scaffold)

```mermaid
flowchart TB
    subgraph Meta["get_available_tools()"]
        T1["rag_search<br/>VBPL đất đai nội bộ"]
        T2["get_exchange_rate<br/>API tỷ giá realtime"]
    end

    subgraph Exec["execute_tool(name, **kwargs)"]
        M[build_tool_map]
        Try[Gọi hàm tool]
        OK[Observation = kết quả str]
        ERR["Observation = [TOOL_ERROR] ...<br/>không raise lên FastAPI"]
        Try -->|OK| OK
        Try -->|Timeout / Connection / RateLimit / ...| ERR
    end

    Meta --> Exec
    Exec -->|str Observation| Loop[ReAct loop — phase 2]
```

**Hợp đồng Observation khi lỗi** (do `format_tool_error_observation`):

```text
[TOOL_ERROR] tool=<name> type=<Timeout|RateLimit|ConnectionError|...>
message=<chi tiết rút gọn ≤300 ký tự>
hint=... Agent tự xử lý tiếp, không crash API ...
```

Nguyên tắc: **lỗi tool ≠ lỗi HTTP 500**. Chỉ orchestration / LLM hệ thống mới được bubble lên `chat.py`.

---

## 6. Hạ tầng Docker Compose

```mermaid
flowchart LR
    API[api :8000<br/>uvicorn] --> Redis[redis :6379]
    API --> ChromaSrv[chromadb :8001]
    API --> VolData[(./data volume)]
```

| Service | Port | Mục đích |
|---------|------|----------|
| `api` | 8000 | FastAPI |
| `redis` | 6379 | Memory / semantic cache (phase 2) |
| `chromadb` | 8001 | Vector DB server (hiện ingest vẫn dùng local persist `data/chroma`) |

---

## 7. API & cấu hình

| Method | Path | Body / Response |
|--------|------|-----------------|
| `GET` | `/health` | `{ status, version }` |
| `POST` | `/chat` | `ChatRequest` → `ChatResponse` |

**Biến môi trường chính** (xem `.env.example`):

- `GOOGLE_API_KEY`, `GOOGLE_MODEL`, `EMBEDDING_MODEL`
- `CHROMA_PERSIST_DIR`, `DATA_DIR`
- `CHUNK_SIZE`, `CHUNK_OVERLAP`, `TOP_K`
- `REDIS_URL` (phase 2)

---

## 8. Lộ trình

```mermaid
flowchart LR
    subgraph P1["Phase 1 — hiện tại"]
        A1[Ingest PDF/DOCX/DOC<br/>chunk pháp lý]
        A2[Chat: retrieve to Gemini<br/>Chroma local]
        A3[Tool scaffold<br/>Observation an toàn]
    end

    subgraph P2["Phase 2"]
        B1[ReAct + Function Calling<br/>execute_tool trong loop]
        B2[Redis semantic cache<br/>services/cache]
        B3[RBAC metadata filter<br/>services/auth]
    end

    subgraph P3["Phase 3"]
        C1[Reranker<br/>cải thiện precision]
        C2[Ragas eval<br/>faithfulness / relevancy]
    end

    P1 --> P2 --> P3
```

---

## 9. Tài liệu liên quan

| File | Đối tượng |
|------|-----------|
| [architecture.md](./architecture.md) | Hệ thống (tài liệu này) |
| [learning-guide.md](./learning-guide.md) | Học tập / onboarding khái niệm |
| [../README.md](../README.md) | Setup nhanh |

---

*Cập nhật theo codebase hiện tại. Khi ReAct loop / cache / RBAC được merge, bổ sung mục tương ứng vào sơ đồ runtime.*

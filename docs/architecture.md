# Kiến trúc hệ thống — Advanced RAG Agent (Đất đai)

> Tài liệu kỹ thuật cho vận hành / phát triển.  
> Mục tiêu sản phẩm: agent trả lời kiến thức **quy định đất đai** dựa trên kho văn bản nội bộ, sẵn sàng mở rộng ReAct + tool ngoại vi.

**Trạng thái:** Phase 1–2 runtime đã chạy (ReAct + Redis semantic cache + RBAC); Phase 3 (Rerank, Ragas) đang scaffold / thiết kế theo đặc tả dưới đây.

Tài liệu học tập: [learning-guide.md](./learning-guide.md).

---

## 0. Tech stack

| Lớp | Công nghệ | Vai trò |
|-----|-----------|---------|
| Runtime | Python ≥ 3.11 | Ngôn ngữ chính |
| Package / env | **uv** (khuyến nghị) hoặc pip | Cài dependency, venv |
| Orchestration LLM | **LangChain** (+ text-splitters, community loaders) | Ingest, retrieve, tool wiring |
| Vector DB | **ChromaDB** | Lưu embedding + metadata filter |
| LLM / Embedding | **Google Gemini** (Flash family; cấu hình qua `.env`) | Sinh câu trả lời + embed |
| API | **FastAPI** + Uvicorn | HTTP `/health`, `/chat` |
| Cache / memory | **Redis** | Semantic cache + session (phase 2) |
| Đóng gói | **Docker Compose** | `api` + `redis` + `chromadb` |
| Đánh giá | **Ragas** (LLM-as-a-judge) | Faithfulness / chống hallucination |

```mermaid
flowchart LR
    subgraph App
        FastAPI --> LangChain
        LangChain --> Gemini[Gemini Flash]
        LangChain --> Chroma[(ChromaDB)]
        LangChain --> Redis[(Redis)]
    end
    Docker --> App
    uv --> App
```

---

## 1. Tổng quan hệ thống

Hệ thống là API FastAPI nhận câu hỏi: kiểm tra semantic cache → RBAC filter → ReAct agent (tool-calling) → Observation → câu trả lời Gemini. Phase 3 bổ sung rerank + Ragas.

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
        RT[retriever + optional rerank]
    end

    subgraph LLM["app/services/llm"]
        EMB[Embeddings Gemini]
        GEN[LLM Gemini]
        PR[prompts]
    end

    subgraph Data["Lưu trữ"]
        DOC[(data/docs<br/>nguồn VBPL)]
        CH[(data/chroma<br/>vector index)]
        RD[(Redis<br/>semantic cache)]
    end

    U --> H & C
    C --> RA
    RA --> RT
    RA --> PR --> GEN
    RT --> VS --> CH
    IN --> DOC
    IN --> EMB --> CH
    Tools -->|ReAct| RA
    RD -->|TTL + versioning| RA
```

| Thành phần | Vai trò | Trạng thái |
|------------|---------|------------|
| FastAPI (`/health`, `/chat`) | HTTP, thin wrapper | ✅ |
| Agent `run_agent` | ReAct loop + tool-calling | ✅ |
| RAG ingest | Load, chunk pháp lý, embed, persist Chroma | ✅ |
| RAG retrieve | Similarity search top-k (+ metadata `where`) | ✅ |
| Gemini LLM + embeddings | Sinh câu trả lời / vector | ✅ |
| Tools + `execute_tool` | Metadata tool + Observation an toàn khi lỗi | ✅ |
| ReAct loop đầy đủ | Thought → Action → Observation lặp | ✅ |
| Redis semantic cache | TTL + versioning, chặn câu hỏi lặp | ✅ |
| RBAC metadata filter | Pre-filter `where` trong Chroma | ✅ |
| Reranking | Lấy ~20 chunk → giữ top 5 | 🔲 phase 3 |
| Ragas Faithfulness | LLM-as-a-judge, kiểm soát hallucination | 🔲 phase 3 |

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
        redis_c[redis.py]
    end
    subgraph models["models/"]
        sch[schemas]
    end
    subgraph services["services/"]
        rag[rag/]
        agent[agent/]
        llm[llm/]
        cache[cache/]
        auth[auth/]
    end

    routes -->|gọi| agent
    agent -->|retrieve| rag
    agent -->|prompt + invoke| llm
    agent -->|hit/miss| cache
    agent -->|build filter| auth
    cache --> redis_c
    rag --> cfg
    llm --> cfg
    routes --> sch
    deps --> auth
```

| Thư mục | Trách nhiệm | Không làm |
|---------|-------------|-----------|
| `app/api` | HTTP, validate request/response | Business RAG / LLM |
| `app/core` | Settings `.env`, Redis client | Logic nghiệp vụ |
| `app/models` | Pydantic schemas | I/O DB / LLM |
| `app/services/rag` | Ingest, chunk, Chroma, retrieve, rerank | Chọn tool / HTTP |
| `app/services/agent` | Orchestration, tool metadata, an toàn tool | Chi tiết embedding |
| `app/services/llm` | Client Gemini, prompts | Routing HTTP |
| `app/services/cache` | Semantic cache Redis | Gọi Chroma / LLM sinh câu |
| `app/services/auth` | Role → metadata filter RBAC | Query vector |
| `eval/` | Ragas (Faithfulness, …) | Runtime API |
| `data/docs` | Tài liệu nguồn | — |
| `data/chroma` | Index vector (gitignore) | — |

**Vị trí thiết kế — SoC đã chốt:**

| Concern | Đặt tại |
|---------|---------|
| Semantic Cache (Redis + TTL/version) | `services/cache/semantic.py` + `core/redis.py` |
| RBAC → metadata filter | `services/auth/rbac.py`; identity ở `api/deps.py` |
| Apply `where` lúc retrieve | `services/rag/retriever.py` (nhận filter, không biết role) |
| Reranker | `services/rag/rerank.py` (nhận candidates, trả top-n) |

---

## 3. Dữ liệu & lưu trữ (pipeline)

Chuỗi chuẩn:

**RecursiveCharacterTextSplitter (có overlap) → Embedding (Gemini) → ChromaDB**

```mermaid
flowchart LR
    A[Thư mục DATA_DIR<br/>data/docs] --> B{Phần mở rộng}
    B -->|.pdf| C1[PyPDFLoader]
    B -->|.docx| C2[Docx2txtLoader]
    B -->|.doc| C3[LegacyDocLoader<br/>Word COM]
    C1 & C2 & C3 --> D[Document + metadata<br/>source, filename, filetype]
    D --> E[RecursiveCharacterTextSplitter<br/>LEGAL_SEPARATORS + overlap]
    E --> F[Gemini Embeddings]
    F --> G[(ChromaDB<br/>data/chroma)]
```

**API ingest chính:**

| Hàm | Mô tả |
|-----|--------|
| `ingest_file(path)` | Một file theo suffix |
| `ingest_directory(dir?)` | Đệ quy PDF + DOCX + DOC |
| `get_legal_text_splitter()` | Separators: Chương → Mục → Điều → Khoản → điểm |

**Tham số mặc định:** `chunk_size=1000`, `chunk_overlap=200` (`app/core/config.py`).

Overlap giữ ngữ cảnh biên giữa hai chunk; separators pháp lý tránh cắt giữa `Điều` / `Khoản`.

---

## 4. Luồng runtime `/chat` (Phase 2 — đang chạy)

```mermaid
sequenceDiagram
    participant Client
    participant Chat as api/routes/chat.py
    participant Deps as api/deps UserContext
    participant RBAC as auth/rbac
    participant Agent as agent/react.run_agent
    participant Cache as cache/semantic
    participant Tools as agent/tools.execute_tool
    participant Ret as rag/retriever
    participant Chroma as data/chroma
    participant LLM as llm Gemini + bind_tools

    Client->>Chat: POST /chat { query } + X-User-Role?
    Chat->>Deps: get_user_context(header)
    Deps-->>Chat: role
    Chat->>RBAC: role_to_where(role)
    RBAC-->>Chat: where filter
    Chat->>Agent: run_agent(query, where, role)

    Agent->>Cache: get_cached_answer(query, scope=role)
    alt cache hit (cosine ≥ threshold + TTL + version)
        Cache-->>Agent: { answer, sources }
    else cache miss
        loop ReAct ≤ max_iterations
            Agent->>LLM: messages + tools
            LLM-->>Agent: AIMessage (text hoặc tool_calls)
            opt có tool_calls
                Agent->>Tools: execute_tool(name, where, …)
                alt rag_search
                    Tools->>Ret: retrieve_documents(query, where)
                    Ret->>Chroma: similarity + metadata where
                    Chroma-->>Tools: Documents
                else get_exchange_rate / lỗi
                    Tools-->>Agent: Observation str hoặc [TOOL_ERROR]
                end
                Tools-->>Agent: Observation → ToolMessage
            end
        end
        Agent->>Cache: set_cached_answer(TTL + corpus_version)
    end

    Agent-->>Chat: { answer, query, sources }
    Chat-->>Client: ChatResponse
```

**Điểm chốt Phase 2:**

| Lớp | Hành vi |
|-----|---------|
| Header `X-User-Role` | `citizen` \| `staff` \| `legal_staff` (mặc định `citizen`) |
| RBAC | `role_to_where` → `{"audience": {"$in": [...]}}` truyền vào `rag_search` |
| Semantic cache | Cosine embedding + `CACHE_SIMILARITY_THRESHOLD` + `CORPUS_VERSION` + scope theo role |
| ReAct | `bind_tools` → `rag_search` / `get_exchange_rate` qua `execute_tool` |
| Rerank | Chưa — Phase 3 |

**Luồng mục tiêu Phase 3** (bổ sung rerank sau retrieve rộng):

```mermaid
flowchart TB
    Q[Query] --> SC{Semantic cache<br/>hit?}
    SC -->|hit + còn TTL| ANS[Trả answer cached]
    SC -->|miss| RBAC[RBAC build where filter]
    RBAC --> REACT[ReAct / rag_search]
    REACT --> RET[Retrieve ~20 chunks<br/>Chroma + metadata]
    RET --> RR[Rerank → top 5]
    RR --> LLM[Gemini generate]
    LLM --> STORE[Ghi cache<br/>TTL + corpus_version]
    STORE --> ANS2[Trả answer]
```

---

## 5. Agent Tools & an toàn Observation

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
    Exec -->|str Observation| Loop[ReAct loop]
```

**Hợp đồng Observation khi lỗi** (do `format_tool_error_observation`):

```text
[TOOL_ERROR] tool=<name> type=<Timeout|RateLimit|ConnectionError|...>
message=<chi tiết rút gọn ≤300 ký tự>
hint=... Agent tự xử lý tiếp, không crash API ...
```

Nguyên tắc: **lỗi tool ≠ lỗi HTTP 500**. Chỉ orchestration / LLM hệ thống mới được bubble lên `chat.py`.

Agent dùng **ReAct loop + Function Calling**; tool ngoại vi (ví dụ tỷ giá) luôn đi qua `execute_tool` (try/except → Observation).

---

## 6. Tối ưu & mở rộng

### 6.1 Semantic Cache (Redis + TTL + Versioning)

**Mục tiêu:** chặn câu hỏi lặp / gần nghĩa → giảm gọi retrieve + LLM, giảm tải hệ thống.

| Thành phần | Mô tả |
|------------|--------|
| Key | Embedding của query (hoặc hash gần đúng) + `corpus_version` |
| Value | `answer` (+ optional `sources`) đã serialize |
| TTL | Hết hạn tự động (ví dụ 1h–24h, cấu hình `.env`) |
| Versioning | Khi re-ingest / đổi index → tăng `corpus_version` → cache cũ coi như miss |

```mermaid
flowchart TB
    Q[Query] --> E[Embed query]
    E --> L[Lookup Redis<br/>nearest + version khớp?]
    L -->|hit + TTL còn| HIT[Return cached answer]
    L -->|miss / hết hạn / sai version| MISS[Chạy RAG + LLM đầy đủ]
    MISS --> W[SET Redis<br/>TTL + corpus_version]
```

**File đã có:** `app/services/cache/semantic.py`, client `app/core/redis.py`.

| Env | Mặc định | Ý nghĩa |
|-----|----------|---------|
| `REDIS_URL` | `redis://localhost:6379/0` | Kết nối Redis; lỗi/offline → bỏ qua cache |
| `CACHE_TTL_SECONDS` | `3600` | TTL entry + index set |
| `CORPUS_VERSION` | `1` | Tăng khi re-ingest / đổi index |
| `CACHE_SIMILARITY_THRESHOLD` | `0.92` | Ngưỡng cosine để coi là hit |

### 6.2 Reranking (20 → top 5)

**Mục tiêu:** retrieve rộng để không bỏ sót, rồi xếp hạng lại trước khi đưa vào prompt.

| Bước | Số lượng | Ý nghĩa |
|------|----------|---------|
| Retrieve | ~20 chunks | Recall cao |
| Rerank | giữ **top 5** | Precision cao, context gọn |

**Hiệu quả kỳ vọng (đặc tả sản phẩm):**

| Chỉ số | Ước lượng |
|--------|-----------|
| Giảm context đưa vào LLM | ~**75%** (20 → 5) |
| Tiết kiệm chi phí API | ~**65%** |
| Giảm latency | ~**20–35%** |

```mermaid
flowchart LR
    Q[Query] --> R[Chroma retrieve k=20]
    R --> RR[Reranker]
    RR --> T5[Top 5 chunks]
    T5 --> P[Prompt + Gemini]
```

**File dự kiến:** `app/services/rag/rerank.py`; gọi từ retriever/agent sau similarity search.

### 6.3 Bảo mật — Metadata Pre-filtering (RBAC) trong ChromaDB

**Mục tiêu:** user chỉ retrieve được chunk thuộc phạm vi quyền — filter **ngay trong Chroma** (`where`), không lọc sau khi đã lấy hết.

Ví dụ metadata gắn lúc ingest:

| Field | Ví dụ giá trị |
|-------|----------------|
| `audience` | `public`, `internal`, `legal_staff` |
| `doc_level` | `law`, `decree`, `circular`, `guide` |
| `region` | `nationwide`, `province_x` |

Ví dụ: role `citizen` → `where = {"audience": {"$in": ["public"]}}`.

```mermaid
flowchart TB
    REQ[Request + identity] --> DEP[api/deps<br/>UserContext]
    DEP --> POL[services/auth/rbac<br/>role to where]
    POL --> RET[retriever<br/>similarity + where]
    RET --> CH[(ChromaDB)]
    CH -->|chỉ chunk được phép| CTX[Context an toàn]
```

**SoC:** `auth` quyết định filter; `retriever` chỉ apply; không hard-code role trong Chroma query builder.

**Runtime:** `chat.py` → `role_to_where(user.role)` → `run_agent(..., where=..., role=...)`. Ingest mặc định gắn `audience=public`; tài liệu `internal` / `legal_staff` cần metadata tương ứng rồi re-ingest.

---

## 7. Đánh giá — Ragas (LLM-as-a-judge)

**Mục tiêu:** đo **Faithfulness** — câu trả lời có bám context đã retrieve không → kiểm soát **hallucination** (ảo giác điều/khoản).

| Khái niệm | Ý nghĩa |
|-----------|---------|
| LLM-as-a-judge | Model chấm điểm câu trả lời theo rubric / metric Ragas |
| Faithfulness | Claim trong answer có được hỗ trợ bởi context không |
| Eval offline | Chạy trên bộ hỏi–đáp mẫu trong `eval/` — không chặn request realtime |

```mermaid
flowchart LR
    DS[Dataset<br/>question + context + answer] --> RG[Ragas]
    RG --> F[Faithfulness score]
    F --> REP[Báo cáo / CI]
```

**Chạy (scaffold):** `python -m eval.run_ragas`  
**Phụ thuộc optional:** `.[eval]` trong `pyproject.toml`.

---

## 8. Hạ tầng Docker Compose

```mermaid
flowchart LR
    API[api :8000<br/>uvicorn] --> Redis[redis :6379]
    API --> ChromaSrv[chromadb :8001]
    API --> VolData[(./data volume)]
```

| Service | Port | Mục đích |
|---------|------|----------|
| `api` | 8000 | FastAPI |
| `redis` | 6379 | Semantic cache + memory (phase 2) |
| `chromadb` | 8001 | Vector DB server (hiện ingest vẫn dùng local persist `data/chroma`) |

---

## 9. API & cấu hình

| Method | Path | Body / Response |
|--------|------|-----------------|
| `GET` | `/health` | `{ status, version }` |
| `POST` | `/chat` | `ChatRequest` → `ChatResponse` |

**Biến môi trường chính** (xem `.env.example`):

- `GOOGLE_API_KEY`, `GOOGLE_MODEL`, `EMBEDDING_MODEL`
- `CHROMA_PERSIST_DIR`, `DATA_DIR`
- `CHUNK_SIZE`, `CHUNK_OVERLAP`, `TOP_K`
- `REDIS_URL`, `CACHE_TTL_SECONDS`, `CORPUS_VERSION`, `CACHE_SIMILARITY_THRESHOLD` (Phase 2)
- Header RBAC: `X-User-Role` (`citizen` \| `staff` \| `legal_staff`)
- *(Phase 3 dự kiến)* `RETRIEVE_K`, `RERANK_TOP_N`

---

## 10. Lộ trình

```mermaid
flowchart LR
    subgraph P1["Phase 1 — xong"]
        A1[Ingest PDF/DOCX/DOC<br/>chunk pháp lý + overlap]
        A2[Chat: retrieve to Gemini<br/>Chroma local]
        A3[Tool scaffold<br/>Observation an toàn]
    end

    subgraph P2["Phase 2 — hiện tại"]
        B1[ReAct + Function Calling<br/>execute_tool trong loop]
        B2[Redis semantic cache<br/>TTL + versioning]
        B3[RBAC metadata filter<br/>Chroma where]
    end

    subgraph P3["Phase 3"]
        C1[Rerank 20 to top 5<br/>giảm context / cost / latency]
        C2[Ragas Faithfulness<br/>LLM-as-a-judge]
    end

    P1 --> P2 --> P3
```

---

## 11. Tài liệu liên quan

| File | Đối tượng |
|------|-----------|
| [architecture.md](./architecture.md) | Hệ thống (tài liệu này) |
| [learning-guide.md](./learning-guide.md) | Học tập / onboarding khái niệm |
| [../README.md](../README.md) | Setup nhanh |

---

*Phase 2 đã merge (ReAct, Redis semantic cache, RBAC). Phase 3 (rerank KPI, Ragas Faithfulness) đang scaffold / thiết kế.*

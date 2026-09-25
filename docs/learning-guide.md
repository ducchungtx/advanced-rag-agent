# Hướng dẫn học tập — Agent RAG quy định đất đai

> Tài liệu mang tính **học tập / onboarding**.  
> Đọc để hiểu *vì sao* hệ thống được thiết kế vậy, không phải sổ tay vận hành chi tiết.  
> Tài liệu hệ thống: [architecture.md](./architecture.md).

---

## 1. Bài toán đang giải

Người dùng hỏi về **quy định đất đai** (thu hồi, bồi thường, cấp GCN, chuyển mục đích…).  
LLM đơn thuần dễ bịa điều luật → cần **RAG**: lấy đoạn văn bản thật từ kho nội bộ rồi mới trả lời.

```mermaid
flowchart LR
    Q[Câu hỏi người dùng] --> R{Có ngữ cảnh<br/>từ văn bản?}
    R -->|Không — LLM thuần| H[Rủi ro hallucinate<br/>điều/khoản sai]
    R -->|Có — RAG| A[Trả lời dựa trên<br/>chunk đã retrieve]
```

**Ý chính:** Agent không “biết luật” sẵn trong trọng số mô hình cho đủ độ tin cậy pháp lý; nó **tra cứu** kho đã index.

---

## 2. Stack cần nhớ (bức tranh lớn)

```mermaid
flowchart TB
    UV[uv / pip] --> PY[Python + FastAPI]
    PY --> LC[LangChain]
    LC --> G[Gemini Flash]
    LC --> CH[(ChromaDB)]
    LC --> RD[(Redis cache)]
    PY --> DK[Docker Compose]
    EV[Ragas eval] -.->|offline| G
```

Không cần thuộc hết API: chỉ cần biết **ai làm việc gì** — FastAPI nhận request, LangChain nối RAG/tools, Chroma nhớ kiến thức, Redis nhớ câu hỏi lặp, Gemini viết câu trả lời, Ragas chấm độ trung thực.

---

## 3. RAG là gì — nhìn bằng hình

**RAG = Retrieval-Augmented Generation**

1. **Retrieval:** tìm đoạn văn liên quan trong vector DB  
2. **Augmented:** nhét các đoạn đó vào prompt  
3. **Generation:** LLM viết câu trả lời dựa trên ngữ cảnh đó  

```mermaid
flowchart TB
    subgraph Offline["Offline — làm một lần / khi có VBPL mới"]
        DOC[Văn bản Word/PDF] --> CHUNK[RecursiveCharacterTextSplitter<br/>có overlap] --> EMB1[Embedding] --> DB[(Chroma)]
    end

    subgraph Online["Online — mỗi câu hỏi"]
        Q[Query] --> EMB2[Embedding query]
        EMB2 --> SEARCH[Similarity search]
        DB --> SEARCH
        SEARCH --> CTX[Top-k chunks]
        CTX --> PROMPT[Prompt + câu hỏi]
        PROMPT --> LLM[Gemini] --> ANS[Câu trả lời + sources]
    end
```

| Khái niệm | Trong project này |
|-----------|-------------------|
| Document | File Luật / NĐ / TT / hướng dẫn |
| Chunk | Đoạn text sau khi split (ưu tiên theo Điều/Khoản) |
| Overlap | Phần chồng giữa hai chunk — tránh mất câu ở biên |
| Embedding | Vector số từ Gemini embedding model |
| Vector store | Chroma tại `data/chroma` |
| top_k | Số chunk lấy về (mặc định 4; Phase 3 sẽ retrieve rộng rồi rerank) |

---

## 4. Vì sao văn bản pháp luật cần chunk đặc biệt?

Cắt theo dấu `.` dễ **xé giữa “Điều 1.”** → mất nghĩa pháp lý.

```mermaid
flowchart TB
    subgraph Bad["Cách cắt kém"]
        B1["... theo Điều 1."] --> B2[". Người sử dụng đất ..."]
        B2 -.->|mất ngữ cảnh Điều| B3[Chunk mồ côi]
    end

    subgraph Good["LEGAL_SEPARATORS trong ingest"]
        G1[Chương] --> G2[Mục] --> G3[Điều] --> G4[Khoản] --> G5[điểm / đoạn / câu]
    end
```

**Ghi nhớ học tập:** với VBPL, *thứ tự ưu tiên cắt* quan trọng hơn việc chỉnh `chunk_size` vài trăm ký tự. Overlap vẫn cần để “dính” biên Điều dài.

---

## 5. Agent vs RAG thuần — lộ trình tư duy

**Phase 1 (nền tảng):** luôn retrieve rồi trả lời — đơn giản, ổn cho “chỉ hỏi luật”.

**Phase 2 (đã chạy):** Agent **tự chọn tool** (ReAct + Function Calling):

- `rag_search` → kho đất đai nội bộ  
- `get_exchange_rate` → API ngoại vi (tỷ giá…)  

```mermaid
flowchart TB
    U[User: câu hỏi] --> A[Agent Gemini]
    A --> D{Cần thông tin gì?}
    D -->|Quy định đất đai| T1[Tool: rag_search]
    D -->|Tỷ giá realtime| T2[Tool: get_exchange_rate]
    D -->|Đủ kiến thức chung| F[Trả lời trực tiếp]
    T1 --> OBS[Observation]
    T2 --> OBS
    OBS --> A
    A --> OUT[Final Answer]
```

**Bài học:** *description* của tool là “hướng dẫn sử dụng” cho model. Hai tool cố ý **phủ định lẫn nhau** để giảm gọi nhầm.

---

## 6. ReAct + Observation khi tool lỗi

ReAct ≈ vòng lặp: **Reason → Act → Observe → …**

Khi API tỷ giá timeout, **không** để exception làm sập FastAPI — trả **Observation lỗi** (`execute_tool` + try/except):

```mermaid
sequenceDiagram
    participant A as Agent
    participant E as execute_tool
    participant API as API ngoại vi

    A->>E: Action get_exchange_rate
    E->>API: HTTP request
    API-->>E: Timeout / 429 / ConnectionError
    E-->>A: Observation [TOOL_ERROR] type=Timeout ...
    Note over A: Thought: tỷ giá tạm lỗi,<br/>vẫn trả lời phần pháp lý bằng rag_search
    A->>E: Action rag_search
    E-->>A: Observation = chunks VBPL
    A-->>A: Final Answer không crash API
```

| Tầng | Ví dụ | Xử lý đúng |
|------|--------|------------|
| Tool | Timeout tỷ giá | → Observation `[TOOL_ERROR]` |
| Agent | Hết số bước ReAct | → Trả lời lịch sự / partial |
| API HTTP | Bug code, LLM key sai | → HTTP 500 |

---

## 7. Semantic Cache — vì sao cần TTL và Versioning?

Câu hỏi lặp (“thu hồi đất được bồi thường thế nào?”) không nên mỗi lần đều gọi đủ retrieve + LLM.

```mermaid
flowchart TB
    Q1[Câu hỏi gần giống] --> C{Redis có<br/>answer còn hạn?}
    C -->|Có + đúng version| FAST[Trả ngay — giảm tải]
    C -->|Không / hết TTL / đổi corpus| FULL[Chạy RAG đầy đủ rồi SET cache]
```

| Ý tưởng | Học gì từ đó |
|---------|----------------|
| **Semantic** | So theo *nghĩa* (embedding), không chỉ chuỗi ký tự giống hệt |
| **TTL** | Kiến thức / tỷ giá / chính sách có “tuổi thọ” — hết hạn thì tính lại |
| **Versioning** | Sau khi ingest lại VBPL, tăng version → tránh trả answer cũ dựa index cũ |

Chi tiết kỹ thuật: [architecture.md §6.1](./architecture.md).

---

## 8. Reranking — lấy nhiều rồi lọc ít

Similarity search giỏi **recall** (không bỏ sót) nhưng prompt dài thì đắt và nhiễu.

```mermaid
flowchart LR
    A[Retrieve ~20] --> B[CrossEncoder] --> C[Top 5 vào prompt]
```

**Hình dung:** đọc 20 trang nháp → chỉ giữ 5 đoạn thật sự khớp câu hỏi.  
Thuật toán trong project: **cross-encoder local** (`sentence-transformers`) — chấm từng cặp (query, chunk), không tốn quota Gemini embed.  
Đặc tả kỳ vọng: giảm ~75% context, ~65% chi phí API generate (xem architecture).

---

## 9. RBAC bằng Metadata Pre-filtering

Không phải “lấy hết rồi che”. Chroma nhận `where` **trước / khi** search → chunk ngoài quyền không lọt vào context.

```mermaid
flowchart LR
    Role[citizen] --> F["where audience in public"]
    F --> CH[(Chroma)]
    CH --> OK[Chỉ văn bản công khai]
```

Học SoC: `deps` biết *ai*; `rbac` biết *filter gì*; `retriever` chỉ *áp dụng filter*.

---

## 10. Ragas & Faithfulness — đo ảo giác

**Hallucination:** answer nêu Điều/Khoản không có trong context.  
**Faithfulness (Ragas):** LLM-as-a-judge chấm “mỗi claim có được context chống lưng không?”.

```mermaid
flowchart TB
    CTX[Context đã retrieve] --> J[Ragas judge]
    ANS[Answer của agent] --> J
    J --> S[Faithfulness score]
    S --> D{Đạt ngưỡng?}
    D -->|Không| FIX[Sửa prompt / retrieve / rerank]
    D -->|Có| OK[An tâm hơn khi ship]
```

Eval chạy **offline** (`eval/`) — khác với cache/rerank chạy trên đường request.

---

## 11. SoC — tách mối quan tâm

```mermaid
flowchart TB
    subgraph Đúng["Mỗi lớp một việc"]
        API[api — cửa HTTP]
        AG[agent — điều phối]
        RAG[rag — tìm và lưu vector + rerank]
        CACHE[cache — nhớ câu hỏi tương tự]
        AUTH[auth/rbac — ai được xem gì]
        LLM[llm — nói chuyện với Gemini]
    end

    API --> AG
    AG --> RAG
    AG --> CACHE
    AG --> AUTH
    AG --> LLM
    AUTH -.->|chỉ tạo filter| RAG
```

**Câu hỏi kiểm tra:**

- Redis semantic cache viết trong `chat.py`? → **Không** (`services/cache`).  
- Role hard-code trong `retriever.py`? → **Không** (`auth` tạo filter).  
- Chroma cần file PDF lúc query? → **Không** — cần text đã embed.  
- Ragas chạy trên mỗi `/chat`? → **Không bắt buộc** — eval offline.

---

## 12. Bản đồ kiến thức ↔ file trong repo

```mermaid
flowchart TB
    ROOT[Advanced RAG - Dat dai]

    ROOT --> HTTP[HTTP]
    ROOT --> RAG[RAG]
    ROOT --> AG[Agent]
    ROOT --> CACHE[Cache]
    ROOT --> AUTH[Auth]
    ROOT --> LLM[LLM]
    ROOT --> EVAL[Eval]
    ROOT --> CFG[Config]
    ROOT --> DATA[Data]

    HTTP --> H1["api/routes/chat.py"]
    HTTP --> H2["api/routes/health.py"]
    HTTP --> H3["models/schemas.py"]

    RAG --> R1[ingest.py]
    RAG --> R2[retriever.py]
    RAG --> R3[vectorstore.py]
    RAG --> R4[rerank.py]

    AG --> A1[react.py]
    AG --> A2[tools.py]

    CACHE --> C1[semantic.py]
    AUTH --> AU1[rbac.py]

    LLM --> L1[client.py]
    LLM --> L2[prompts.py]

    EVAL --> E1[run_ragas.py]

    CFG --> CF1["core/config.py"]
    CFG --> CF2[".env"]

    DATA --> D1["data/docs"]
    DATA --> D2["data/chroma"]
```

---

## 13. Thực hành gợi ý

1. **Ingest:** bỏ VBPL vào `DATA_DIR`, chạy `ingest_directory()`, xem số chunk (mặc định `audience=public`).  
2. **Retrieve smoke:** hỏi rõ Điều/Khoản, đối chiếu chunk.  
3. **Chat:** `POST /chat` — kiểm tra `sources`; thử header `X-User-Role: citizen|staff|legal_staff`.  
4. **Tool description:** đọc hai description trong `tools.py`.  
5. **Lỗi an toàn:** `execute_tool("get_exchange_rate")` → `[TOOL_ERROR]`, không traceback client.  
6. **Semantic cache (Phase 2):** bật Redis (`docker compose up -d redis`), hỏi trùng / gần nghĩa 2 lần — lần 2 kỳ vọng cache hit (log). Đổi `CORPUS_VERSION` sau re-ingest.  
7. **Rerank (Phase 3):** `python -u scripts/rerank_smoke.py` — so thứ tự trước/sau.  
8. **Ragas:** `uv run --extra eval python -m eval.run_ragas` — đọc Faithfulness.

---

## 14. Thuật ngữ nhanh

| Thuật ngữ | Nghĩa ngắn |
|-----------|------------|
| Hallucination | Model bịa nội dung không có trong nguồn |
| Embedding | Biểu diễn vector của text để so độ tương đồng |
| Chunk overlap | Phần chồng giữa hai chunk để giữ ngữ cảnh biên |
| Function Calling | Model chọn hàm/tool kèm tham số có cấu trúc |
| Observation | Kết quả tool đưa lại vào vòng ReAct |
| Semantic cache | Cache theo độ giống nghĩa + TTL/version |
| Metadata pre-filter | Lọc bằng metadata trong Chroma (RBAC) |
| Reranking | Xếp lại candidates sau retrieve, giữ top-n |
| Faithfulness | Metric Ragas: answer bám context |
| LLM-as-a-judge | Dùng LLM chấm điểm câu trả lời / metric |

---

## 15. Đọc tiếp

1. [architecture.md](./architecture.md) — stack, tối ưu, RBAC, Ragas, Docker, lộ trình  
2. [../README.md](../README.md) — cài đặt và chạy nhanh  
3. Code: `app/services/agent/react.py`, `app/services/agent/tools.py`, `app/services/cache/semantic.py`, `app/services/auth/rbac.py`

---

*Tài liệu học tập — ưu tiên trực quan và khái niệm. Runtime hiện tại là Phase 3 (ReAct + cache + RBAC + rerank; Ragas offline); chi tiết triển khai lấy từ codebase và architecture.md.*

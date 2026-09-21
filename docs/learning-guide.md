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

## 2. RAG là gì — nhìn bằng hình

**RAG = Retrieval-Augmented Generation**

1. **Retrieval:** tìm đoạn văn liên quan trong vector DB  
2. **Augmented:** nhét các đoạn đó vào prompt  
3. **Generation:** LLM viết câu trả lời dựa trên ngữ cảnh đó  

```mermaid
flowchart TB
    subgraph Offline["Offline — làm một lần / khi có VBPL mới"]
        DOC[Văn bản Word/PDF] --> CHUNK[Cắt chunk] --> EMB1[Embedding] --> DB[(Chroma)]
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
| Embedding | Vector số từ Gemini embedding model |
| Vector store | Chroma tại `data/chroma` |
| top_k | Số chunk lấy về (mặc định 4) |

---

## 3. Vì sao văn bản pháp luật cần chunk đặc biệt?

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

**Ghi nhớ học tập:** với VBPL, *thứ tự ưu tiên cắt* quan trọng hơn việc chỉnh `chunk_size` vài trăm ký tự.

---

## 4. Agent vs RAG thuần — lộ trình tư duy

**Phase 1 (đang chạy):** luôn retrieve rồi trả lời — đơn giản, ổn cho “chỉ hỏi luật”.

**Phase 2 (đang chuẩn bị):** Agent **tự chọn tool**:

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

**Bài học:** *description* của tool là “hướng dẫn sử dụng” cho model. Hai tool cố ý **phủ định lẫn nhau** (RAG không dùng cho tỷ giá; tỷ giá không dùng cho VBPL) để giảm gọi nhầm.

---

## 5. ReAct + Observation khi tool lỗi

ReAct ≈ vòng lặp: **Reason (Thought) → Act (gọi tool) → Observe (đọc kết quả) → …**

Khi API tỷ giá timeout, **không được** để exception làm sập FastAPI. Thay vào đó trả **Observation lỗi** để Agent tự xử lý:

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
    A-->>A: Final Answer (không crash API)
```

**Ba tầng lỗi cần tách trong đầu:**

| Tầng | Ví dụ | Xử lý đúng |
|------|--------|------------|
| Tool | Timeout tỷ giá | → Observation `[TOOL_ERROR]` |
| Agent | Hết số bước ReAct | → Trả lời lịch sự / partial |
| API HTTP | Bug code, LLM key sai | → HTTP 500 |

---

## 6. SoC — tách mối quan tâm (để học thiết kế)

```mermaid
flowchart TB
    subgraph Đúng["Mỗi lớp một việc"]
        API[api — cửa HTTP]
        AG[agent — điều phối]
        RAG[rag — tìm & lưu vector]
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

**Câu hỏi kiểm tra hiểu biết:**

- Redis semantic cache có nên viết trong `chat.py` không? → **Không** (đặt `services/cache`).  
- RBAC có nên hard-code role trong `retriever.py` không? → **Không** (`auth` tạo filter; `retriever` chỉ apply).  
- Chroma có cần file PDF không? → **Không**; cần **text đã embed**. PDF/DOCX chỉ là nguồn ingest.

---

## 7. Bản đồ kiến thức ↔ file trong repo

```mermaid
mindmap
  root((Advanced RAG<br/>Đất đai))
    HTTP
      api/routes/chat.py
      api/routes/health.py
      models/schemas.py
    RAG
      ingest.py
      retriever.py
      vectorstore.py
    Agent
      react.py
      tools.py
    LLM
      client.py
      prompts.py
    Config
      core/config.py
      .env
    Data
      data/docs
      data/chroma
```

---

## 8. Thực hành gợi ý (học bằng làm)

1. **Ingest:** bỏ vài file VBPL vào `DATA_DIR`, chạy `ingest_directory()`, xem số chunk.  
2. **Retrieve smoke:** hỏi một câu rõ Điều/Khoản, xem chunk trả về có đúng văn bản không.  
3. **Chat:** `POST /chat` — đối chiếu `sources` với file gốc.  
4. **Tool description:** đọc `RAG_SEARCH_DESCRIPTION` vs `EXCHANGE_RATE_DESCRIPTION` — thử tự viết description cho tool mới (ví dụ “tra cứu phí”).  
5. **Lỗi an toàn:** gọi `execute_tool("get_exchange_rate")` — phải nhận chuỗi `[TOOL_ERROR]`, không traceback ra client.

---

## 9. Thuật ngữ nhanh

| Thuật ngữ | Nghĩa ngắn |
|-----------|------------|
| Hallucination | Model bịa nội dung không có trong nguồn |
| Embedding | Biểu diễn vector của text để so độ tương đồng |
| Chunk overlap | Phần chồng giữa hai chunk để giữ ngữ cảnh biên |
| Function Calling | Model chọn hàm/tool kèm tham số có cấu trúc |
| Observation | Kết quả tool đưa lại vào vòng ReAct |
| Semantic cache | Cache theo độ giống nghĩa của câu hỏi (thường qua embedding) |
| Metadata pre-filter | Lọc chunk theo field metadata trước/ khi search (phục vụ RBAC) |

---

## 10. Đọc tiếp

1. [architecture.md](./architecture.md) — sơ đồ hệ thống, API, Docker, lộ trình phase  
2. [../README.md](../README.md) — cài đặt và chạy nhanh  
3. Code thực tế: `app/services/rag/ingest.py`, `app/services/agent/tools.py`

---

*Tài liệu học tập — ưu tiên trực quan và khái niệm. Chi tiết triển khai lấy từ codebase và architecture.md.*

"""
Đánh giá Faithfulness (Ragas) trên pipeline RAG hiện tại.

Cần:
  uv sync --extra eval
  GOOGLE_API_KEY trong .env

Chạy (live — cần embed quota + Chroma đã ingest):
  uv run --extra eval python -m eval.run_ragas

Chạy (fixture — chỉ chấm Faithfulness, không gọi Chroma/embed):
  uv run --extra eval python -m eval.run_ragas --fixture
"""

from __future__ import annotations

import argparse
import logging
import sys

logger = logging.getLogger(__name__)

# Dataset nội bộ — ground_truth/reference dùng cho metrics khác; Faithfulness
# chỉ cần question + answer + retrieved_contexts.
EVAL_DATASET = [
    {
        "question": "Thời hạn giải quyết thủ tục thu hồi đất và bồi thường là bao lâu?",
        "ground_truth": (
            "Trả lời dựa trên văn bản hướng dẫn Luật Đất đai đã index trong kho nội bộ."
        ),
    },
    {
        "question": "Điều kiện chuyển nhượng quyền sử dụng đất theo quy định hiện hành?",
        "ground_truth": (
            "Trả lời dựa trên điều kiện chuyển nhượng QSDĐ trong tài liệu đã ingest."
        ),
    },
]

# Mẫu offline: answer bám context → Faithfulness kỳ vọng cao.
FIXTURE_ROWS = [
    {
        "question": "Thời hạn Chủ tịch UBND cấp xã ra quyết định thu hồi đất là bao lâu?",
        "answer": (
            "Theo ngữ cảnh, trong thời hạn không quá 03 ngày, Chủ tịch Ủy ban nhân dân "
            "cấp xã ra quyết định thu hồi đất."
        ),
        "contexts": [
            "2. Trong thời hạn không quá 03 ngày, Chủ tịch Ủy ban nhân dân cấp xã "
            "ra quyết định thu hồi đất. IV. Trình tự, thủ tục bồi thường."
        ],
        "ground_truth": "Không quá 03 ngày.",
    },
    {
        "question": "Sau quyết định thu hồi đất, cơ quan quản lý đất đai trình gì trong 10 ngày?",
        "answer": (
            "Trong thời hạn 10 ngày kể từ ngày có quyết định thu hồi đất, cơ quan có "
            "chức năng quản lý đất đai trình cơ quan có thẩm quyền phê duyệt."
        ),
        "contexts": [
            "Trong thời hạn 10 ngày kể từ ngày có quyết định thu hồi đất, cơ quan có "
            "chức năng quản lý đất đai trình cơ quan có thẩm quyền."
        ],
        "ground_truth": "Trình cơ quan có thẩm quyền trong 10 ngày.",
    },
]


def _build_rows_live() -> list[dict]:
    """1 lần retrieve/câu (đã rerank) + sinh answer từ context — tiết kiệm embed."""
    from langchain_core.messages import HumanMessage, SystemMessage

    from app.services.llm.client import get_llm
    from app.services.rag.retriever import retrieve_documents

    llm = get_llm()
    rows: list[dict] = []
    for item in EVAL_DATASET:
        question = item["question"]
        docs = retrieve_documents(question)
        contexts = [d.page_content for d in docs]
        if not contexts:
            logger.warning("Không có context cho %r — bỏ qua", question)
            continue
        joined = "\n\n---\n\n".join(contexts)
        messages = [
            SystemMessage(
                content=(
                    "Bạn trả lời tiếng Việt dựa CHỈ trên ngữ cảnh đã cho. "
                    "Không bịa điều/khoản ngoài ngữ cảnh."
                )
            ),
            HumanMessage(
                content=f"Ngữ cảnh:\n{joined}\n\nCâu hỏi: {question}\n\nTrả lời:"
            ),
        ]
        answer = str(llm.invoke(messages).content)
        rows.append(
            {
                "question": question,
                "answer": answer,
                "contexts": contexts,
                "ground_truth": item.get("ground_truth", ""),
            }
        )
        logger.info(
            "Prepared q=%r contexts=%s answer_len=%s",
            question[:60],
            len(contexts),
            len(answer),
        )
    return rows


def _run_faithfulness(rows: list[dict]) -> None:
    # Dùng metric legacy + LangchainLLMWrapper (sync) — collections API đòi async client.
    import warnings

    from datasets import Dataset
    from ragas import evaluate
    from ragas.llms import LangchainLLMWrapper
    from ragas.metrics import Faithfulness

    from app.core.config import settings
    from app.services.llm.client import get_llm

    if not settings.google_api_key:
        print("Thiếu GOOGLE_API_KEY trong .env", file=sys.stderr)
        sys.exit(1)

    if not rows:
        print("Không có mẫu để đánh giá.", file=sys.stderr)
        sys.exit(1)

    dataset = Dataset.from_list(
        [
            {
                "user_input": row["question"],
                "response": row["answer"],
                "retrieved_contexts": row["contexts"],
            }
            for row in rows
        ]
    )

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        evaluator_llm = LangchainLLMWrapper(get_llm())
        metric = Faithfulness(llm=evaluator_llm)
        result = evaluate(dataset=dataset, metrics=[metric], llm=evaluator_llm)

    print(result)
    try:
        scores = result.to_pandas()
        print("\nChi tiết:")
        cols = [
            c
            for c in ("user_input", "question", "faithfulness")
            if c in scores.columns
        ]
        print(
            scores[cols].to_string(index=False)
            if cols
            else scores.to_string(index=False)
        )
    except Exception:  # noqa: BLE001
        pass


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Ragas Faithfulness eval")
    parser.add_argument(
        "--fixture",
        action="store_true",
        help="Dùng mẫu offline (không gọi Chroma / embed)",
    )
    args = parser.parse_args(argv)

    try:
        from ragas.metrics import Faithfulness  # noqa: F401
    except ImportError:
        print(
            "Thiếu deps Ragas. Cài: uv sync --extra eval\n"
            "Rồi chạy lại: uv run --extra eval python -m eval.run_ragas",
            file=sys.stderr,
        )
        sys.exit(1)

    if args.fixture:
        print(f"Ragas Faithfulness (fixture) — {len(FIXTURE_ROWS)} mẫu")
        _run_faithfulness(FIXTURE_ROWS)
        return

    print(f"Ragas Faithfulness (live) — {len(EVAL_DATASET)} câu hỏi")
    try:
        rows = _build_rows_live()
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Live pipeline thất bại (%s) — fallback --fixture",
            exc,
        )
        print(
            "Cảnh báo: live thất bại (thường do hết quota embed). "
            "Đang chạy --fixture.",
            file=sys.stderr,
        )
        rows = FIXTURE_ROWS
    _run_faithfulness(rows)


if __name__ == "__main__":
    main()

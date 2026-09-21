"""
CLI / script đánh giá RAG bằng Ragas (Faithfulness, Answer Relevancy, ...).

Chạy (sau khi cài deps):
  uv run python -m eval.run_ragas
"""

from __future__ import annotations

# Placeholder — phase 3: nối Ragas với dataset câu hỏi nội bộ.
EVAL_DATASET = [
    {
        "question": "Thời gian ăn trưa là lúc mấy giờ?",
        "ground_truth": "Điền câu trả lời chuẩn từ tài liệu nội bộ.",
    },
]


def main() -> None:
    print("Ragas evaluation scaffold.")
    print(f"Số câu hỏi mẫu: {len(EVAL_DATASET)}")
    print("TODO: implement Faithfulness / Answer Relevancy với Ragas.")


if __name__ == "__main__":
    main()

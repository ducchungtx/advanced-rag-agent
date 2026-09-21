"""Ingest PDF/DOCX vào Chroma vector store (tối ưu văn bản pháp luật VN)."""

from pathlib import Path

from langchain_chroma import Chroma
from langchain_community.document_loaders import DirectoryLoader, Docx2txtLoader, PyPDFLoader
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.core.config import settings
from app.services.llm.client import get_embeddings

# Ưu tiên cắt theo đơn vị pháp lý trước khi cắt theo câu/ký tự.
# Tránh cắt giữa Điều / Khoản chỉ vì gặp dấu "." (vd. "Điều 1.", "Khoản 2.").
LEGAL_SEPARATORS = [
    "\n\nChương ",
    "\n\nMục ",
    "\n\nĐiều ",
    "\nChương ",
    "\nMục ",
    "\nĐiều ",
    "\nKhoản ",
    "\nđiểm ",
    "\n\n",
    "\n",
    "; ",
    ". ",
    " ",
    "",
]

_LOADERS = {
    ".pdf": PyPDFLoader,
    ".docx": Docx2txtLoader,
}


def ingest_pdf(path: str | Path) -> int:
    """Load một PDF, chunk và ghi vào Chroma. Trả về số chunk."""
    return ingest_file(path)


def ingest_docx(path: str | Path) -> int:
    """Load một DOCX, chunk và ghi vào Chroma. Trả về số chunk."""
    return ingest_file(path)


def ingest_file(path: str | Path) -> int:
    """Load một file PDF/DOCX theo phần mở rộng, chunk và ghi vào Chroma."""
    file_path = Path(path)
    suffix = file_path.suffix.lower()
    loader_cls = _LOADERS.get(suffix)
    if loader_cls is None:
        supported = ", ".join(sorted(_LOADERS))
        raise ValueError(f"Định dạng không hỗ trợ: {suffix}. Hỗ trợ: {supported}")

    documents = loader_cls(str(file_path)).load()
    _attach_source_metadata(documents, file_path)
    return _persist_documents(documents)


def ingest_directory(directory: str | Path | None = None) -> int:
    """Load tất cả PDF + DOCX trong thư mục (đệ quy) và ghi vào Chroma."""
    data_dir = Path(directory or settings.data_dir)
    if not data_dir.is_dir():
        raise FileNotFoundError(f"Thư mục không tồn tại: {data_dir}")

    documents: list[Document] = []
    for glob_pattern, loader_cls in (
        ("**/*.pdf", PyPDFLoader),
        ("**/*.docx", Docx2txtLoader),
    ):
        loader = DirectoryLoader(
            str(data_dir),
            glob=glob_pattern,
            loader_cls=loader_cls,
            show_progress=True,
        )
        loaded = loader.load()
        for doc in loaded:
            source = Path(doc.metadata.get("source", ""))
            if source.name:
                _attach_source_metadata([doc], source)
        documents.extend(loaded)

    if not documents:
        raise FileNotFoundError(
            f"Không tìm thấy file .pdf/.docx trong {data_dir.resolve()}"
        )

    return _persist_documents(documents)


def get_legal_text_splitter() -> RecursiveCharacterTextSplitter:
    """Splitter ưu tiên cắt theo Chương / Mục / Điều / Khoản."""
    return RecursiveCharacterTextSplitter(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
        separators=LEGAL_SEPARATORS,
        keep_separator=True,
    )


def _attach_source_metadata(documents: list[Document], path: Path) -> None:
    for doc in documents:
        doc.metadata.setdefault("source", str(path))
        doc.metadata.setdefault("filename", path.name)
        doc.metadata.setdefault("filetype", path.suffix.lower().lstrip("."))


def _persist_documents(documents: list[Document]) -> int:
    splitter = get_legal_text_splitter()
    chunks = splitter.split_documents(documents)
    Chroma.from_documents(
        chunks,
        get_embeddings(),
        persist_directory=settings.chroma_persist_dir,
    )
    return len(chunks)

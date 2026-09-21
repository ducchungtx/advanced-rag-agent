"""Ingest PDF/DOCX/DOC vào Chroma vector store (tối ưu văn bản pháp luật VN)."""

from __future__ import annotations

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


class LegacyDocLoader:
    """Load file .doc (Word 97–2003) qua Microsoft Word COM trên Windows."""

    def __init__(self, file_path: str) -> None:
        self.file_path = file_path

    def load(self) -> list[Document]:
        try:
            import win32com.client  # type: ignore[import-untyped]
        except ImportError as exc:
            raise ImportError(
                "Cần pywin32 để đọc .doc. Cài: pip install pywin32"
            ) from exc

        path = str(Path(self.file_path).resolve())
        word = win32com.client.Dispatch("Word.Application")
        word.Visible = False
        try:
            doc = word.Documents.Open(path, ReadOnly=True)
            try:
                text = str(doc.Content.Text or "").strip()
            finally:
                doc.Close(False)
        finally:
            word.Quit()

        if not text:
            return []
        return [Document(page_content=text, metadata={"source": self.file_path})]


_LOADERS = {
    ".pdf": PyPDFLoader,
    ".docx": Docx2txtLoader,
    ".doc": LegacyDocLoader,
}


def ingest_pdf(path: str | Path) -> int:
    """Load một PDF, chunk và ghi vào Chroma. Trả về số chunk."""
    return ingest_file(path)


def ingest_docx(path: str | Path) -> int:
    """Load một DOCX, chunk và ghi vào Chroma. Trả về số chunk."""
    return ingest_file(path)


def ingest_file(path: str | Path) -> int:
    """Load một file PDF/DOCX/DOC theo phần mở rộng, chunk và ghi vào Chroma."""
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
    """Load tất cả PDF + DOCX + DOC trong thư mục (đệ quy) và ghi vào Chroma."""
    data_dir = Path(directory or settings.data_dir)
    if not data_dir.is_dir():
        raise FileNotFoundError(f"Thư mục không tồn tại: {data_dir}")

    documents: list[Document] = []
    for glob_pattern, loader_cls in (
        ("**/*.pdf", PyPDFLoader),
        ("**/*.docx", Docx2txtLoader),
        ("**/*.doc", LegacyDocLoader),
    ):
        # DirectoryLoader với .doc sẽ mở Word nhiều lần — chấp nhận được với số lượng vừa phải.
        if glob_pattern == "**/*.doc":
            loaded = _load_legacy_docs(data_dir)
        else:
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
            f"Không tìm thấy file .pdf/.docx/.doc trong {data_dir.resolve()}"
        )

    return _persist_documents(documents)


def _load_legacy_docs(data_dir: Path) -> list[Document]:
    """Load toàn bộ .doc bằng một phiên Word COM (nhanh hơn mở từng file)."""
    paths = sorted(p for p in data_dir.rglob("*.doc") if p.is_file())
    if not paths:
        return []

    try:
        import win32com.client  # type: ignore[import-untyped]
    except ImportError as exc:
        raise ImportError(
            "Cần pywin32 để đọc .doc. Cài: pip install pywin32"
        ) from exc

    documents: list[Document] = []
    word = win32com.client.Dispatch("Word.Application")
    word.Visible = False
    try:
        for path in paths:
            doc = word.Documents.Open(str(path.resolve()), ReadOnly=True)
            try:
                text = str(doc.Content.Text or "").strip()
            finally:
                doc.Close(False)
            if not text:
                continue
            item = Document(page_content=text, metadata={"source": str(path)})
            _attach_source_metadata([item], path)
            documents.append(item)
            print(f"Loaded .doc: {path.name}")
    finally:
        word.Quit()
    return documents


def get_legal_text_splitter() -> RecursiveCharacterTextSplitter:
    """Splitter ưu tiên cắt theo Chương / Mục / Điều / Khoản."""
    return RecursiveCharacterTextSplitter(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
        separators=LEGAL_SEPARATORS,
        keep_separator=True,
    )


def _attach_source_metadata(
    documents: list[Document],
    path: Path,
    *,
    audience: str = "public",
) -> None:
    """Gắn metadata nguồn + audience (RBAC pre-filter trong Chroma)."""
    for doc in documents:
        doc.metadata.setdefault("source", str(path))
        doc.metadata.setdefault("filename", path.name)
        doc.metadata.setdefault("filetype", path.suffix.lower().lstrip("."))
        doc.metadata.setdefault("audience", audience)


def _persist_documents(documents: list[Document]) -> int:
    splitter = get_legal_text_splitter()
    chunks = splitter.split_documents(documents)
    # Sau re-ingest: tăng CORPUS_VERSION trong .env để semantic cache cũ miss.
    print(
        f"Ingest note: corpus_version hiện tại={settings.corpus_version}. "
        "Sau khi đổi index, tăng CORPUS_VERSION để invalidate semantic cache.",
        flush=True,
    )
    _write_chunks_with_rate_limit(chunks)
    return len(chunks)


def _write_chunks_with_rate_limit(
    chunks: list[Document],
    *,
    batch_size: int = 15,
    pause_seconds: float = 25.0,
    max_retries: int = 20,
) -> None:
    """Ghi chunk vào Chroma; resume theo số vector đã có; retry khi 429."""
    import atexit
    import os
    import time
    from pathlib import Path

    from langchain_google_genai._common import GoogleGenerativeAIError

    persist = Path(settings.chroma_persist_dir)
    persist.mkdir(parents=True, exist_ok=True)
    lock_path = persist / ".ingest.lock"

    def _pid_alive(pid: int) -> bool:
        import subprocess

        out = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}"],
            capture_output=True,
            text=True,
            check=False,
        )
        return str(pid) in out.stdout and "No tasks" not in out.stdout

    # Exclusive create để tránh 2 process chạy song song
    try:
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(str(os.getpid()))
    except FileExistsError:
        try:
            old_pid = int(lock_path.read_text(encoding="utf-8").strip())
        except ValueError:
            old_pid = -1
        if old_pid > 0 and _pid_alive(old_pid):
            raise RuntimeError(f"Ingest đang chạy (pid={old_pid}). Đợi xong rồi chạy lại.")
        lock_path.unlink(missing_ok=True)
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(str(os.getpid()))

    atexit.register(lambda: lock_path.unlink(missing_ok=True))

    store = Chroma(
        persist_directory=settings.chroma_persist_dir,
        embedding_function=get_embeddings(),
    )
    total = len(chunks)
    already = store._collection.count()
    if already >= total:
        print(f"Skip embed — already have {already}/{total} chunks", flush=True)
        return
    if already > 0:
        print(f"Resume from chunk {already + 1}/{total}", flush=True)

    for start in range(already, total, batch_size):
        batch = chunks[start : start + batch_size]
        ids = [f"vbpl-{start + i}" for i in range(len(batch))]
        attempt = 0
        while True:
            try:
                store.add_documents(batch, ids=ids)
                print(
                    f"Embedded chunks {start + 1}-{start + len(batch)}/{total}",
                    flush=True,
                )
                break
            except GoogleGenerativeAIError as exc:
                attempt += 1
                if "RESOURCE_EXHAUSTED" not in str(exc) or attempt > max_retries:
                    raise
                wait = pause_seconds * attempt
                print(
                    f"Rate limited - sleep {wait:.0f}s (retry {attempt}/{max_retries})",
                    flush=True,
                )
                time.sleep(wait)
        if start + batch_size < total:
            time.sleep(pause_seconds)

"""Ingest PDF/DOCX/DOC vào Chroma vector store (tối ưu văn bản pháp luật VN)."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
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

_SOFFICE_CANDIDATES = (
    "soffice",
    "libreoffice",
    "/Applications/LibreOffice.app/Contents/MacOS/soffice",
    "/opt/homebrew/bin/soffice",
    "/usr/local/bin/soffice",
    "/usr/bin/soffice",
    r"C:\Program Files\LibreOffice\program\soffice.exe",
    r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
)


class LegacyDocLoader:
    """Load file .doc (Word 97–2003): Windows dùng Word COM, macOS/Linux dùng LibreOffice."""

    def __init__(self, file_path: str) -> None:
        self.file_path = file_path

    def load(self) -> list[Document]:
        path = Path(self.file_path)
        docs = _load_legacy_doc_paths([path])
        return docs


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
    """Load toàn bộ .doc (Windows: Word COM; macOS/Linux: LibreOffice)."""
    paths = sorted(p for p in data_dir.rglob("*.doc") if p.is_file())
    return _load_legacy_doc_paths(paths)


def _load_legacy_doc_paths(paths: list[Path]) -> list[Document]:
    """Chọn backend đọc .doc theo OS; fallback LibreOffice nếu Word COM không có."""
    if not paths:
        return []

    if sys.platform == "win32":
        try:
            return _load_legacy_docs_win32(paths)
        except ImportError:
            print(
                "pywin32/Word COM không khả dụng — fallback LibreOffice cho .doc",
                flush=True,
            )

    return _load_legacy_docs_libreoffice(paths)


def _load_legacy_docs_win32(paths: list[Path]) -> list[Document]:
    """Load .doc bằng một phiên Microsoft Word COM (Windows)."""
    import win32com.client  # type: ignore[import-untyped]

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
            print(f"Loaded .doc (Word): {path.name}", flush=True)
    finally:
        word.Quit()
    return documents


def _find_soffice() -> str | None:
    """Tìm binary LibreOffice trên macOS / Linux / Windows."""
    for candidate in _SOFFICE_CANDIDATES:
        if os.path.sep in candidate or (sys.platform == "win32" and "\\" in candidate):
            if Path(candidate).is_file():
                return candidate
            continue
        found = shutil.which(candidate)
        if found:
            return found
    return None


def _load_legacy_docs_libreoffice(paths: list[Path]) -> list[Document]:
    """Convert .doc → .txt bằng LibreOffice headless, rồi đọc text."""
    soffice = _find_soffice()
    if not soffice:
        raise RuntimeError(
            "Không đọc được .doc: cần Microsoft Word + pywin32 (Windows) "
            "hoặc LibreOffice (`soffice` trên PATH / macOS: brew install --cask libreoffice)."
        )

    documents: list[Document] = []
    with tempfile.TemporaryDirectory(prefix="rag-doc-") as tmp:
        tmp_dir = Path(tmp)
        # Tên unique tránh đụng basename trùng giữa các thư mục con.
        staging: list[tuple[Path, Path]] = []
        for idx, path in enumerate(paths):
            staged = tmp_dir / f"{idx:04d}_{path.name}"
            try:
                staged.symlink_to(path.resolve())
            except OSError:
                shutil.copy2(path, staged)
            staging.append((path, staged))

        cmd = [
            soffice,
            "--headless",
            "--norestore",
            "--convert-to",
            "txt:Text",
            "--outdir",
            str(tmp_dir),
            *[str(staged) for _, staged in staging],
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            err = (result.stderr or result.stdout or "").strip()
            raise RuntimeError(f"LibreOffice convert .doc thất bại (code={result.returncode}): {err}")

        for path, staged in staging:
            txt_path = tmp_dir / f"{staged.stem}.txt"
            if not txt_path.is_file():
                print(f"Skip .doc (không có txt sau convert): {path.name}", flush=True)
                continue
            text = txt_path.read_text(encoding="utf-8-sig", errors="replace").strip()
            if not text:
                continue
            item = Document(page_content=text, metadata={"source": str(path)})
            _attach_source_metadata([item], path)
            documents.append(item)
            print(f"Loaded .doc (LibreOffice): {path.name}", flush=True)

    return documents


def _pid_alive(pid: int) -> bool:
    """True nếu process còn sống (Windows + Unix)."""
    if pid <= 0:
        return False
    if sys.platform == "win32":
        out = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}"],
            capture_output=True,
            text=True,
            check=False,
        )
        return str(pid) in out.stdout and "No tasks" not in out.stdout
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


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

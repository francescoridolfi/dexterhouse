# SPDX-License-Identifier: AGPL-3.0-or-later
"""File type detection and text extraction for context documents.

`sniff` runs at upload, in the request: it checks the extension against the content and
never parses the file. `extract` runs in the worker (`projects.tasks.process_context`).
"""

import io
import zipfile
from dataclasses import dataclass
from pathlib import PurePosixPath

TEXT_TYPES = {
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".txt": "text/plain",
    ".json": "application/json",
    ".yaml": "application/yaml",
    ".yml": "application/yaml",
    ".csv": "text/csv",
}
PDF = "application/pdf"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
BINARY_TYPES = {".pdf": PDF, ".docx": DOCX}


@dataclass(frozen=True)
class Extracted:
    text: str
    pages: int | None = None


class ExtractionError(Exception):
    """The file is accepted but its text cannot be read; `reason` is a short code."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def sniff(filename: str, content: bytes) -> str:
    """The MIME type of an accepted file.

    Raises:
        ValueError: unsupported extension, or content that does not match it.
    """
    suffix = PurePosixPath(filename).suffix.lower()
    if not content:
        raise ValueError("the file is empty")
    if suffix in TEXT_TYPES:
        if b"\x00" in content[:8192]:
            raise ValueError("binary content in a text file")
        return TEXT_TYPES[suffix]
    if suffix == ".pdf":
        if not content.startswith(b"%PDF-"):
            raise ValueError("not a PDF file")
        return PDF
    if suffix == ".docx":
        if not _is_docx(content):
            raise ValueError("not a DOCX file")
        return DOCX
    allowed = ", ".join(sorted({*TEXT_TYPES, *BINARY_TYPES}))
    raise ValueError(f"unsupported file type (allowed: {allowed})")


def _is_docx(content: bytes) -> bool:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            return "word/document.xml" in archive.namelist()
    except zipfile.BadZipFile:
        return False


#: A DOCX may not inflate past this size, nor by more than MAX_RATIO (zip bombs).
MAX_UNCOMPRESSED = 50 * 1024 * 1024
MAX_RATIO = 100


def extract(mime: str, content: bytes, max_chars: int = 200_000) -> Extracted:
    """Plain text of the file (Markdown headings kept where the format has them).

    Reading stops a little after `max_chars`: the caller cuts and flags the rest.
    """
    if mime in TEXT_TYPES.values():
        return Extracted(text=decode(content))
    if mime == PDF:
        return _pdf(content, max_chars)
    if mime == DOCX:
        return _docx(content)
    raise ExtractionError("unsupported_format")


def _pdf(content: bytes, max_chars: int) -> Extracted:
    from pypdf import PdfReader
    from pypdf.errors import PyPdfError

    try:
        reader = PdfReader(io.BytesIO(content))
        if reader.is_encrypted and not reader.decrypt(""):
            raise ExtractionError("encrypted")
        texts, total = [], 0
        for page in reader.pages:
            text = (page.extract_text() or "").strip()
            texts.append(text)
            total += len(text)
            if total > max_chars:
                break
        pages = len(reader.pages)
    except ExtractionError:
        raise
    except (PyPdfError, ValueError, KeyError, TypeError, OSError, RecursionError):
        raise ExtractionError("unreadable") from None
    text = "\n\n".join(t for t in texts if t)
    if not text:
        raise ExtractionError("no_text_layer")
    return Extracted(text=text, pages=pages)


def _docx(content: bytes) -> Extracted:
    from docx import Document
    from docx.table import Table

    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            inflated = sum(info.file_size for info in archive.infolist())
    except zipfile.BadZipFile:
        raise ExtractionError("unreadable") from None
    if inflated > MAX_UNCOMPRESSED or inflated > MAX_RATIO * max(len(content), 1):
        raise ExtractionError("too_large_uncompressed")
    try:
        document = Document(io.BytesIO(content))
        lines = []
        for block in document.iter_inner_content():
            if isinstance(block, Table):
                lines += [" | ".join(c.text.strip() for c in row.cells) for row in block.rows]
            elif block.text.strip():
                lines.append(_heading(block.style.name if block.style else "") + block.text.strip())
    except (KeyError, ValueError, zipfile.BadZipFile) as exc:
        raise ExtractionError("unreadable") from exc
    return Extracted(text="\n".join(lines))


def _heading(style: str) -> str:
    """`Title` -> "# ", `Heading 2` -> "## ", other styles -> ""."""
    if style == "Title":
        return "# "
    level = style.removeprefix("Heading ").strip()
    return "#" * int(level) + " " if style.startswith("Heading ") and level.isdigit() else ""


def decode(content: bytes) -> str:
    """UTF-8 (BOM removed), else Latin-1, which decodes any byte string."""
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError:
        return content.decode("latin-1")

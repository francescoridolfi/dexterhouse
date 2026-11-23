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


def extract(mime: str, content: bytes) -> Extracted:
    """Plain text of the file (Markdown headings kept where the format has them)."""
    if mime in TEXT_TYPES.values():
        return Extracted(text=decode(content))
    raise ExtractionError("unsupported_format")


def decode(content: bytes) -> str:
    """UTF-8 (BOM removed), else Latin-1, which decodes any byte string."""
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError:
        return content.decode("latin-1")

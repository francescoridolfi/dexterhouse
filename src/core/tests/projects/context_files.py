# SPDX-License-Identifier: AGPL-3.0-or-later
"""PDF and DOCX test files built in code (no binary fixtures in the repository)."""

import io
import zipfile

from docx import Document
from pypdf import PdfWriter


def text_pdf(pages: list[str]) -> bytes:
    """A PDF with one line of Helvetica text per page."""
    objects: list[bytes] = []
    kids = " ".join(f"{3 + 2 * i} 0 R" for i in range(len(pages)))
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode())
    font = 3 + 2 * len(pages)
    for i, line in enumerate(pages):
        stream = f"BT /F1 12 Tf 72 720 Td ({line}) Tj ET".encode()
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {4 + 2 * i} 0 R "
            f"/Resources << /Font << /F1 {font} 0 R >> >> >>".encode()
        )
        objects.append(b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream))
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for n, body in enumerate(objects, start=1):
        offsets.append(out.tell())
        out.write(b"%d 0 obj\n%s\nendobj\n" % (n, body))
    xref = out.tell()
    out.write(b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1))
    for offset in offsets:
        out.write(b"%010d 00000 n \n" % offset)
    out.write(
        b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref)
    )
    return out.getvalue()


def blank_pdf(pages: int = 2) -> bytes:
    """Pages without a text layer, like a scan."""
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=612, height=792)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def encrypted_pdf() -> bytes:
    writer = PdfWriter(clone_from=io.BytesIO(text_pdf(["secret"])))
    password = "pw-for-tests-only"  # pragma: allowlist secret
    writer.encrypt(user_password=password, algorithm="AES-128")
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def docx(paragraphs: list[tuple[str, str]], table: list[list[str]] | None = None) -> bytes:
    """`paragraphs` as (style, text); style is "Title", "Heading 1".."Heading 9" or ""."""
    document = Document()
    for style, text in paragraphs:
        document.add_paragraph(text, style=style or None)
    if table:
        grid = document.add_table(rows=len(table), cols=len(table[0]))
        for r, row in enumerate(table):
            for c, cell in enumerate(row):
                grid.cell(r, c).text = cell
    out = io.BytesIO()
    document.save(out)
    return out.getvalue()


def docx_bomb(uncompressed_mb: int = 60) -> bytes:
    """A valid-looking DOCX whose document.xml inflates to `uncompressed_mb`."""
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        with archive.open("word/document.xml", "w") as entry:
            chunk = b" " * (1024 * 1024)
            for _ in range(uncompressed_mb):
                entry.write(chunk)
    return out.getvalue()

# SPDX-License-Identifier: AGPL-3.0-or-later
"""PDF and DOCX extraction, and hostile files (docs/specs/context-documents.md)."""

import pytest

from dexterhouse.apps.projects.services import context
from dexterhouse.apps.projects.services.extract import (
    DOCX,
    PDF,
    ExtractionError,
    extract,
    sniff,
)
from tests.projects.context_files import blank_pdf, docx, docx_bomb, encrypted_pdf, text_pdf


def test_pdf_text_and_page_count():
    out = extract(PDF, text_pdf(["Booking API", "Waitlist rules", "Last page sentence"]))
    assert out.pages == 3
    assert "Booking API" in out.text
    assert out.text.rstrip().endswith("Last page sentence")


def test_docx_headings_paragraphs_and_tables_in_order():
    content = docx(
        [("Title", "Analysis"), ("Heading 2", "Limits"), ("", "Answer in 200 ms.")],
        table=[["Endpoint", "SLA"], ["/slots", "200 ms"]],
    )
    assert sniff("analysis.docx", content) == DOCX
    out = extract(DOCX, content)
    assert out.text.splitlines()[:3] == ["# Analysis", "## Limits", "Answer in 200 ms."]
    assert "Endpoint | SLA" in out.text
    assert "/slots | 200 ms" in out.text


@pytest.mark.parametrize(
    ("mime", "content", "reason"),
    [
        (PDF, blank_pdf(), "no_text_layer"),
        (PDF, encrypted_pdf(), "encrypted"),
        (PDF, b"%PDF-1.4\nnot really a pdf", "unreadable"),
        (DOCX, docx_bomb(), "too_large_uncompressed"),
    ],
)
def test_hostile_or_unreadable_files_fail_with_a_reason(mime, content, reason):
    with pytest.raises(ExtractionError) as exc:
        extract(mime, content)
    assert exc.value.reason == reason


def test_a_zip_that_is_not_a_docx_is_refused_at_upload():
    import io
    import zipfile

    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        archive.writestr("readme.txt", "hi")
    with pytest.raises(ValueError, match="not a DOCX"):
        sniff("report.docx", out.getvalue())


@pytest.fixture(autouse=True)
def context_dir(settings, tmp_path):
    settings.CONTEXT_DIR = tmp_path / "context"


@pytest.mark.django_db(transaction=True)
def test_uploaded_pdf_is_processed_with_its_pages(project, user):
    doc = context.add_document(
        project, user, filename="Analysis.pdf", content=text_pdf(["one", "two", "three"])
    )
    doc.refresh_from_db()
    assert doc.data["status"] == "processed"
    assert doc.data["pages"] == 3
    assert "three" in doc.content


@pytest.mark.django_db(transaction=True)
def test_scanned_pdf_upload_fails_without_text_layer(project, user):
    doc = context.add_document(project, user, filename="scan.pdf", content=blank_pdf())
    doc.refresh_from_db()
    assert doc.data["status"] == "failed"
    assert doc.data["error"] == "no_text_layer"
    assert doc.content == ""

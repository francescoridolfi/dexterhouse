# SPDX-License-Identifier: AGPL-3.0-or-later
"""Context documents (docs/specs/context-documents.md): upload, limits, lifecycle, memory."""

import hashlib

import pytest

from dexterhouse.apps.events.models import Event
from dexterhouse.apps.gateway.models import ModelProfile
from dexterhouse.apps.memory.models import MemoryChunk
from dexterhouse.apps.projects.models import ArtifactKind, ProjectStatus
from dexterhouse.apps.projects.services import context
from dexterhouse.common.errors import InvalidTransitionError, ValidationFailedError

ANALYSIS = b"# Technical analysis\n\nThe booking API must answer in 200 ms.\n"


@pytest.fixture(autouse=True)
def context_dir(settings, tmp_path):
    settings.CONTEXT_DIR = tmp_path / "context"
    return settings.CONTEXT_DIR


@pytest.fixture
def embed_profile(organization):
    return ModelProfile.objects.create(
        organization=organization, profile="embed", provider="fake", model="hash-1024"
    )


def _types(project) -> list[str]:
    rows = Event.objects.filter(project_id=project.id, type__startswith="context.")
    return list(rows.order_by("created_at", "id").values_list("type", flat=True))


@pytest.mark.django_db(transaction=True)
def test_text_upload_is_processed_stored_and_announced(project, user, context_dir):
    doc = context.add_document(project, user, filename="analysis.md", content=ANALYSIS)
    doc.refresh_from_db()
    assert doc.kind == ArtifactKind.CONTEXT
    assert doc.name == "context/analysis.md"
    assert doc.content == ANALYSIS.decode()
    data = doc.data
    assert data["status"] == "processed"
    assert data["active"] is True
    assert data["mime"] == "text/markdown"
    assert data["size"] == len(ANALYSIS)
    assert data["sha256"] == hashlib.sha256(ANALYSIS).hexdigest()
    assert data["uploaded_by"] == str(user.id)
    assert (context_dir / str(project.id) / data["sha256"]).read_bytes() == ANALYSIS
    assert _types(project) == ["context.added", "context.processed"]


@pytest.mark.django_db(transaction=True)
def test_utf8_bom_and_latin1_are_decoded(project, user):
    bom = context.add_document(project, user, filename="a.txt", content="﻿ciao".encode())
    latin = context.add_document(project, user, filename="b.csv", content="caffè".encode("latin-1"))
    bom.refresh_from_db()
    latin.refresh_from_db()
    assert bom.content == "ciao"
    assert latin.content == "caffè"


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("filename", "content", "reason"),
    [
        ("tool.exe", b"MZ", "unsupported file type"),
        ("notes.md", b"\x00\x01binary", "binary"),
        ("empty.txt", b"", "empty"),
        ("fake.pdf", b"hello", "not a PDF"),
    ],
)
def test_bad_files_are_refused_and_nothing_is_stored(
    project, user, context_dir, filename, content, reason
):
    with pytest.raises(ValidationFailedError) as exc:
        context.add_document(project, user, filename=filename, content=content)
    assert exc.value.errors[0]["field"] == "file"
    assert reason in exc.value.errors[0]["message"]
    assert not project.artifacts.filter(kind=ArtifactKind.CONTEXT).exists()
    assert not context_dir.exists() or not any(context_dir.rglob("*"))


@pytest.mark.django_db
def test_size_and_count_limits(project, user, settings):
    settings.CONTEXT_MAX_BYTES = 10
    with pytest.raises(ValidationFailedError, match="larger than"):
        context.add_document(project, user, filename="big.txt", content=b"x" * 11)
    settings.CONTEXT_MAX_BYTES = 1000
    settings.CONTEXT_MAX_DOCUMENTS = 2
    for n in range(2):
        context.add_document(project, user, filename=f"d{n}.txt", content=b"text")
    with pytest.raises(ValidationFailedError, match="at most 2"):
        context.add_document(project, user, filename="d3.txt", content=b"text")
    # Re-uploading an existing name is a new version, not a new document.
    again = context.add_document(project, user, filename="d0.txt", content=b"new text")
    assert again.version == 2


@pytest.mark.django_db(transaction=True)
def test_long_text_is_truncated_and_flagged(project, user, settings):
    settings.CONTEXT_MAX_CHARS = 5
    doc = context.add_document(project, user, filename="long.txt", content=b"abcdefgh")
    doc.refresh_from_db()
    assert doc.content == "abcde"
    assert doc.data["truncated"] is True


@pytest.mark.django_db(transaction=True)
def test_memory_indexes_active_documents_and_forgets_deactivated(project, user, embed_profile):
    doc = context.add_document(project, user, filename="analysis.md", content=ANALYSIS)
    chunks = MemoryChunk.objects.filter(project=project, kind="context")
    assert chunks.exists()
    assert all(c.untrusted for c in chunks)
    gone = context.deactivate_document(project, user, doc.name)
    assert gone.version == 2
    assert gone.data["active"] is False
    assert not MemoryChunk.objects.filter(project=project, kind="context").exists()
    assert context.active_documents(project) == []
    assert _types(project)[-1] == "context.deactivated"


@pytest.mark.django_db(transaction=True)
def test_reupload_replaces_the_memory_of_the_older_version(project, user, embed_profile):
    context.add_document(project, user, filename="a.md", content=b"# A\n\nfirst version")
    context.add_document(project, user, filename="a.md", content=b"# A\n\nsecond version")
    texts = MemoryChunk.objects.filter(project=project, kind="context").values_list(
        "content", flat=True
    )
    assert texts
    assert all("second" in t for t in texts)
    assert [d.version for d in context.active_documents(project)] == [2]


@pytest.mark.django_db
def test_archived_projects_refuse_documents(project, user):
    project.status = ProjectStatus.ARCHIVED
    project.save(update_fields=["status"])
    with pytest.raises(InvalidTransitionError):
        context.add_document(project, user, filename="a.md", content=b"text")


@pytest.mark.django_db
def test_deactivating_twice_or_an_unknown_document_fails(project, user):
    doc = context.add_document(project, user, filename="a.md", content=b"text")
    context.deactivate_document(project, user, doc.name)
    with pytest.raises(InvalidTransitionError):
        context.deactivate_document(project, user, doc.name)
    with pytest.raises(ValidationFailedError):
        context.deactivate_document(project, user, "context/none.md")

# SPDX-License-Identifier: AGPL-3.0-or-later
"""Context documents: files the user imports to steer the agents (docs/specs/context-documents.md).

A document is an artifact of kind `context` named `context/<file name>`: `content` is the
extracted text, `data` the metadata. Version 1 is created `processing` at upload and
completed in place by the worker (`process_document`); a re-upload of the same name or a
deactivation is a new version. The original file is kept under `CONTEXT_DIR` by SHA-256.
"""

import hashlib
import uuid
from pathlib import Path, PurePosixPath
from typing import Any

from django.conf import settings
from django.db import transaction
from django.db.models import Max
from django.utils.text import slugify

from dexterhouse.apps.accounts.models import User
from dexterhouse.apps.projects.models import Artifact, ArtifactKind, Project, ProjectStatus
from dexterhouse.apps.projects.services.actors import emit, user_actor
from dexterhouse.apps.projects.services.artifacts import content_hash, index, ref, save_artifact
from dexterhouse.apps.projects.services.extract import ExtractionError, extract, sniff
from dexterhouse.common.errors import InvalidTransitionError, ValidationFailedError

PREFIX = "context/"
PROCESSING, PROCESSED, FAILED = "processing", "processed", "failed"


def document_name(filename: str) -> str:
    """`context/<slug>.<ext>`: a stable name, so a re-upload is a new version."""
    path = PurePosixPath(filename.replace("\\", "/")).name
    stem, suffix = PurePosixPath(path).stem, PurePosixPath(path).suffix.lower()
    return f"{PREFIX}{(slugify(stem) or 'document')[:120]}{suffix}"


def stored_path(project_id: uuid.UUID, sha256: str) -> Path:
    return Path(settings.CONTEXT_DIR) / str(project_id) / sha256


def latest_documents(project: Project, *, include_inactive: bool = False) -> list[Artifact]:
    """Latest version of every document, oldest first."""
    rows = Artifact.objects.filter(project=project, kind=ArtifactKind.CONTEXT)
    latest = {r["name"]: r["v"] for r in rows.values("name").annotate(v=Max("version"))}
    docs = [a for a in rows.order_by("created_at") if latest.get(a.name) == a.version]
    return [d for d in docs if include_inactive or (d.data or {}).get("active")]


def active_documents(project: Project) -> list[Artifact]:
    return latest_documents(project)


def _invalid(message: str) -> ValidationFailedError:
    return ValidationFailedError(message, [{"field": "file", "message": message}])


def _check_open(project: Project) -> None:
    if project.status == ProjectStatus.ARCHIVED:
        raise InvalidTransitionError("archived projects cannot change their context")


def add_document(
    project: Project,
    user: User,
    *,
    filename: str,
    content: bytes,
    title: str = "",
    change_request_id: uuid.UUID | None = None,
) -> Artifact:
    """Store the file, create the `processing` version and queue the text extraction."""
    _check_open(project)
    if len(content) > settings.CONTEXT_MAX_BYTES:
        raise _invalid(f"the file is larger than {settings.CONTEXT_MAX_BYTES} bytes")
    try:
        mime = sniff(filename, content)
    except ValueError as exc:
        raise _invalid(str(exc)) from None
    name = document_name(filename)
    with transaction.atomic():
        Project.objects.select_for_update().filter(pk=project.pk).first()  # serialise the count
        others = [
            d
            for d in latest_documents(project)
            if d.name != name and d.data.get("status") != FAILED
        ]
        if len(others) >= settings.CONTEXT_MAX_DOCUMENTS:
            raise _invalid(f"a project holds at most {settings.CONTEXT_MAX_DOCUMENTS} documents")
        sha = hashlib.sha256(content).hexdigest()
        path = stored_path(project.id, sha)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        data = {
            "filename": PurePosixPath(filename.replace("\\", "/")).name[:200],
            "title": title[:200],
            "mime": mime,
            "size": len(content),
            "sha256": sha,
            "status": PROCESSING,
            "active": True,
            "uploaded_by": str(user.id),
            "change_request": str(change_request_id) if change_request_id else None,
        }
        artifact = save_artifact(project, kind=ArtifactKind.CONTEXT, name=name, data=data)
        emit(
            project,
            "context.added",
            {"artifact": ref(artifact), "filename": data["filename"], "size": data["size"]},
            actor=user_actor(user),
        )
        transaction.on_commit(lambda: _queue(artifact.id))
    return artifact


def _queue(artifact_id: uuid.UUID) -> None:
    from dexterhouse.apps.projects.tasks import process_context

    process_context.delay(str(artifact_id))


def process_document(artifact_id: uuid.UUID) -> str:
    """Worker side: extract the text and mark the version `processed` or `failed`."""
    artifact = Artifact.objects.select_related("project").get(pk=artifact_id)
    data = artifact.data or {}
    if data.get("status") != PROCESSING:
        return data.get("status", "")
    path = stored_path(artifact.project_id, data["sha256"])
    try:
        if not path.is_file():
            raise ExtractionError("missing_file")
        out = extract(data["mime"], path.read_bytes())
        if not out.text.strip():
            raise ExtractionError("no_text")
    except ExtractionError as exc:
        return fail_document(artifact, exc.reason)
    text = out.text[: settings.CONTEXT_MAX_CHARS]
    done = {
        **data,
        "status": PROCESSED,
        "chars": len(text),
        "pages": out.pages,
        "truncated": len(out.text) > len(text),
    }
    payload = {"chars": done["chars"], "pages": out.pages, "truncated": done["truncated"]}
    _complete(artifact, text, done, "context.processed", payload)
    transaction.on_commit(lambda: _index(artifact))
    return PROCESSED


def fail_document(artifact: Artifact, reason: str) -> str:
    data = {**(artifact.data or {}), "status": FAILED, "error": reason}
    _complete(artifact, "", data, "context.failed", {"reason": reason})
    return FAILED


def _complete(
    artifact: Artifact, text: str, data: dict[str, Any], event: str, payload: dict[str, Any]
) -> None:
    with transaction.atomic():
        artifact.content, artifact.data = text, data
        artifact.content_hash = content_hash(text, data)
        artifact.save(update_fields=["content", "data", "content_hash", "updated_at"])
        emit(artifact.project, event, {"artifact": ref(artifact), **payload})


def _index(artifact: Artifact) -> None:
    """Older versions of the document leave the memory before this one enters it."""
    from dexterhouse.apps.memory.services.indexing import forget

    forget(artifact.project_id, ArtifactKind.CONTEXT, artifact.name)
    index(artifact)


def deactivate_document(project: Project, user: User, name: str) -> Artifact:
    """A new version with `active: false`; its chunks leave the memory."""
    from dexterhouse.apps.memory.services.indexing import forget

    _check_open(project)
    latest = next(
        (d for d in latest_documents(project, include_inactive=True) if d.name == name), None
    )
    if latest is None:
        raise ValidationFailedError(
            "unknown document", [{"field": "document", "message": f"{name} not found"}]
        )
    if not latest.data.get("active"):
        raise InvalidTransitionError(f"{name} is already deactivated")
    with transaction.atomic():
        data = {**latest.data, "active": False, "deactivated_by": str(user.id)}
        artifact = save_artifact(
            project, kind=ArtifactKind.CONTEXT, name=name, content=latest.content, data=data
        )
        forget(project.id, ArtifactKind.CONTEXT, name)
        emit(project, "context.deactivated", {"artifact": ref(artifact)}, actor=user_actor(user))
    return artifact

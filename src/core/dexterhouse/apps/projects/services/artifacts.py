# SPDX-License-Identifier: AGPL-3.0-or-later
"""Versioned artifacts: one row per (kind, name, version), structured `data` validated."""

import difflib
import hashlib
import json
import uuid
from typing import Any

from django.db import transaction
from django.db.models import Max
from pydantic import ValidationError

from dexterhouse.apps.projects.models import Artifact, ArtifactKind, Project
from dexterhouse.common.errors import ValidationFailedError
from dexterhouse_schema import STRUCTURED_KINDS, validate_artifact

USER_KINDS = frozenset({ArtifactKind.FILE, ArtifactKind.BRIEF, ArtifactKind.STACK})


def content_hash(content: str, data: Any) -> str:
    raw = content if data is None else json.dumps(data, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def validate_data(kind: str, data: Any) -> dict[str, Any] | None:
    """Validate `data` for structured kinds; text kinds carry no data."""
    if kind not in STRUCTURED_KINDS:
        if data is not None:
            raise ValidationFailedError(
                f"{kind} artifacts carry content, not data",
                [{"field": "data", "message": "must be null for text kinds"}],
            )
        return None
    try:
        model = validate_artifact(kind, data)
    except ValidationError as exc:
        errors = [
            {"field": "data." + ".".join(str(p) for p in e["loc"]), "message": e["msg"]}
            for e in exc.errors(include_url=False)
        ]
        raise ValidationFailedError(f"invalid {kind} data", errors) from None
    return model.model_dump(mode="json")


def save_artifact(
    project: Project,
    *,
    kind: str,
    name: str,
    content: str = "",
    data: Any = None,
    phase_run_id: uuid.UUID | None = None,
    turn_id: uuid.UUID | None = None,
    role: str = "",
) -> Artifact:
    """Create the next version of (kind, name); a `stack` also updates `project.stack`."""
    clean = validate_data(kind, data)
    latest = Artifact.objects.filter(project=project, kind=kind, name=name).aggregate(
        v=Max("version")
    )["v"]
    artifact = Artifact.objects.create(
        project=project,
        kind=kind,
        name=name,
        version=(latest or 0) + 1,
        content=content,
        data=clean,
        content_hash=content_hash(content, clean),
        phase_run_id=phase_run_id,
        produced_by_turn_id=turn_id,
        produced_by_role=role,
    )
    if kind == ArtifactKind.STACK:
        project.stack = clean
        project.save(update_fields=["stack", "updated_at"])
    transaction.on_commit(lambda: index(artifact))
    return artifact


def index(artifact: Artifact) -> None:
    """Send the artifact version to the project memory (`memory.tasks.index_artifact`)."""
    from dexterhouse.apps.memory.tasks import index_artifact_task

    index_artifact_task.delay(
        str(artifact.project.organization_id),
        str(artifact.project_id),
        str(artifact.id),
        artifact.version,
        artifact.kind,
        artifact.name,
        content=artifact.content if artifact.data is None else None,
        data=artifact.data,
    )


def ref(artifact: Artifact) -> dict[str, Any]:
    """`ArtifactRef` of the event catalogue."""
    return {"id": artifact.id, "kind": artifact.kind, "version": artifact.version}


def versions(artifact: Artifact) -> list[Artifact]:
    return list(
        Artifact.objects.filter(
            project_id=artifact.project_id, kind=artifact.kind, name=artifact.name
        ).order_by("version")
    )


def _text(artifact: Artifact) -> str:
    if artifact.data is not None:
        return json.dumps(artifact.data, indent=2, sort_keys=True) + "\n"
    return artifact.content


def diff(artifact: Artifact, against: int) -> str:
    """Unified diff from version `against` to `artifact`."""
    other = Artifact.objects.filter(
        project_id=artifact.project_id, kind=artifact.kind, name=artifact.name, version=against
    ).first()
    if other is None:
        raise ValidationFailedError(
            f"version {against} does not exist",
            [{"field": "against", "message": "unknown version"}],
        )
    lines = difflib.unified_diff(
        _text(other).splitlines(keepends=True),
        _text(artifact).splitlines(keepends=True),
        fromfile=f"{artifact.name}@v{other.version}",
        tofile=f"{artifact.name}@v{artifact.version}",
    )
    return "".join(lines)

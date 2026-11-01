# SPDX-License-Identifier: AGPL-3.0-or-later
"""Notes to the team: they enter the context of the next turns (F-004)."""

import uuid

from dexterhouse.apps.accounts.models import User
from dexterhouse.apps.projects.models import Note, Project
from dexterhouse.apps.projects.services.actors import emit, user_actor
from dexterhouse.common.errors import ConflictError

EXCERPT_CHARS = 140


def add_note(
    project: Project, user: User, content: str, phase_run_id: uuid.UUID | None = None
) -> Note:
    note = Note.objects.create(
        project=project, author=user, content=content, phase_run_id=phase_run_id
    )
    emit(
        project,
        "note.added",
        {"note_id": note.id, "phase_run_id": phase_run_id, "excerpt": content[:EXCERPT_CHARS]},
        actor=user_actor(user),
    )
    return note


def delete_note(note: Note) -> None:
    """Only notes no turn has read yet can be deleted."""
    if note.consumed_by_turn_ids:
        raise ConflictError("the note was already read by an agent")
    note.delete()

# SPDX-License-Identifier: AGPL-3.0-or-later
"""Notes to the team: they enter the context of the next turns and the memory (F-004)."""

import uuid
from typing import Any

from django.db import transaction

from dexterhouse.apps.accounts.models import User
from dexterhouse.apps.projects.models import Note, Project
from dexterhouse.apps.projects.services.actors import agent_actor, emit, user_actor
from dexterhouse.common.errors import ConflictError, InvalidTransitionError

EXCERPT_CHARS = 140
CURRENT = "current"
_LIVE_PHASES = ("running", "waiting_gate", "reopened", "ready")


def current_phase_run(project: Project) -> uuid.UUID:
    """The phase the team is working on now (first live phase in process order)."""
    from dexterhouse.apps.workflows.models import PhaseRun

    row = (
        PhaseRun.objects.filter(process_run__project=project, status__in=_LIVE_PHASES)
        .order_by("position")
        .values_list("pk", flat=True)
        .first()
    )
    if row is None:
        raise InvalidTransitionError("no phase is running: send the note to all phases")
    return row


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
    transaction.on_commit(lambda: index(note))
    return note


def index(note: Note) -> None:
    """Send the note to the project memory (`memory.tasks.index_comment`, kind `note`)."""
    from dexterhouse.apps.memory.tasks import index_comment_task

    index_comment_task.delay(
        str(note.project.organization_id),
        str(note.project_id),
        str(note.id),
        note.content,
        kind="note",
    )


def delete_note(note: Note) -> None:
    """Only notes no turn has read yet can be deleted."""
    if note.consumed_by_turn_ids:
        raise ConflictError("the note was already read by an agent")
    note.delete()


def consume(
    project: Project, note_ids: list[Any], turn_id: uuid.UUID, agent_id: uuid.UUID, role: str
) -> list[Note]:
    """Record that a turn read these notes (`note.consumed`, once per note and turn)."""
    consumed = []
    rows = Note.objects.select_for_update().filter(project=project, pk__in=note_ids)
    for note in rows.order_by("created_at"):
        if turn_id in note.consumed_by_turn_ids:
            continue
        note.consumed_by_turn_ids = [*note.consumed_by_turn_ids, turn_id]
        note.save(update_fields=["consumed_by_turn_ids", "updated_at"])
        emit(
            project,
            "note.consumed",
            {"note_id": note.id, "agent_id": agent_id},
            actor=agent_actor(agent_id, role),
        )
        consumed.append(note)
    return consumed

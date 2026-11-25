# SPDX-License-Identifier: AGPL-3.0-or-later
"""Project state machine (state_machines/project.md): the only place that writes `status`."""

from django.utils import timezone

from dexterhouse.apps.projects.models import Project, ProjectStatus
from dexterhouse.common.errors import InvalidTransitionError, check_transition

S = ProjectStatus
ALLOWED: dict[str, frozenset[str]] = {
    S.DRAFT: frozenset({S.RUNNING, S.ARCHIVED}),
    S.RUNNING: frozenset({S.WAITING, S.PAUSED, S.COMPLETED, S.FAILED}),
    S.WAITING: frozenset({S.RUNNING, S.PAUSED, S.FAILED}),
    S.PAUSED: frozenset({S.RUNNING, S.WAITING, S.FAILED}),
    S.COMPLETED: frozenset({S.RUNNING, S.ARCHIVED}),  # running: a change request (E-13)
    S.FAILED: frozenset({S.RUNNING, S.ARCHIVED}),
    S.ARCHIVED: frozenset(),
}
ACTIVE = frozenset({S.RUNNING, S.WAITING, S.PAUSED})


def transition(
    project: Project, target: str, *, waiting_reason: str | None = None, reopen: bool = False
) -> None:
    """Validate and apply `project.status -> target`; the caller emits the event.

    `completed -> running` needs `reopen`, which only `start_change_request` passes.

    Raises:
        InvalidTransitionError: the state machine has no such transition.
    """
    check_transition("project", project.status, target, ALLOWED)
    if project.status == S.COMPLETED and target == S.RUNNING and not reopen:
        raise InvalidTransitionError("a completed project reopens only with a change request")
    now = timezone.now()
    project.status = target
    project.waiting_reason = waiting_reason if target == S.WAITING else None
    fields = ["status", "waiting_reason", "updated_at"]
    if target == S.RUNNING and project.started_at is None:
        project.started_at = now
        fields.append("started_at")
    if target == S.COMPLETED or reopen:
        project.completed_at = None if reopen else now  # set again when the iteration ends
        fields.append("completed_at")
    if target == S.ARCHIVED:
        project.deleted_at = now
        fields.append("deleted_at")
    project.save(update_fields=fields)

# SPDX-License-Identifier: AGPL-3.0-or-later
"""Iterations driven by change requests (ADR-0018): start, queue, completion, failure.

Every function expects the project row to be locked (`workflows.engine.common.lock`).
"""

from typing import Any

import structlog
from django.db import transaction
from django.utils import timezone

from dexterhouse.apps.accounts.models import User
from dexterhouse.apps.observability.services import budget
from dexterhouse.apps.observability.services.estimate import estimate
from dexterhouse.apps.projects.models import (
    ArtifactKind,
    ChangeRequest,
    ChangeRequestStatus,
    Project,
    ProjectStatus,
)
from dexterhouse.apps.projects.services.actors import SYSTEM, emit, user_actor
from dexterhouse.apps.projects.services.artifacts import save_artifact
from dexterhouse.apps.projects.services.change_requests import set_status
from dexterhouse.apps.projects.services.transitions import transition
from dexterhouse.common.errors import DomainError, InvalidTransitionError

logger = structlog.get_logger(__name__)
CR = ChangeRequestStatus


def _payload(cr: ChangeRequest, **extra: Any) -> dict[str, Any]:
    return {"change_request_id": cr.id, "number": cr.number, **extra}


def _document(cr: ChangeRequest) -> str:
    return f"# {cr.label}: {cr.title}\n\n{cr.body}\n"


def start_change_request(project: Project, cr: ChangeRequest, user: User | None) -> None:
    """queued -> running: reopen the `completed` project on a new run (iteration = n).

    The only caller of `completed -> running`. The CR budget is added to the project's.
    """
    from dexterhouse.apps.workflows.engine import start
    from dexterhouse.apps.workflows.registry import get_process
    from dexterhouse.apps.workspaces.services import prepare_for_iteration

    if project.status != ProjectStatus.COMPLETED:
        raise InvalidTransitionError("a change request starts only on a completed project")
    budget.ensure_org_can_start(project.organization)
    actor = user_actor(user) if user else SYSTEM
    installed = get_process(project.process_name, project.organization_id)
    run = start.create_run(project, installed.process, iteration=cr.number)
    run.project = project
    cr.process_run = run
    cr.started_at = timezone.now()
    set_status(cr, CR.RUNNING, "process_run", "started_at")
    if cr.budget > 0:
        old = project.budget
        project.budget = old + cr.budget
        project.save(update_fields=["budget", "updated_at"])
        emit(project, "project.budget_changed", {"old": old, "new": project.budget}, actor=actor)
    transition(project, ProjectStatus.RUNNING, reopen=True)
    save_artifact(
        project, kind=ArtifactKind.CHANGE_REQUEST, name=f"cr-{cr.number}.md", content=_document(cr)
    )
    payload = _payload(cr, iteration=run.iteration, process_run_id=run.id)
    emit(project, "change_request.started", payload, actor=actor)
    reopened = {"change_request": cr.id, "number": cr.number, "iteration": run.iteration}
    emit(project, "project.reopened", reopened, actor=actor)
    guess = estimate(project.organization_id, project.process_name, len(cr.body))
    emit(project, "budget.estimated", {k: guess[k] for k in ("low", "high", "basis")})
    prepare_for_iteration(project)
    start.start_run(run)


def start_next_change_request(project: Project, user: User | None) -> ChangeRequest | None:
    """Start the oldest `queued` CR of a `completed` project, if any."""
    if project.status != ProjectStatus.COMPLETED:
        return None
    rows = ChangeRequest.objects.select_for_update().filter(project=project, status=CR.QUEUED)
    cr = rows.order_by("number").first()
    if cr is not None:
        start_change_request(project, cr, user)
    return cr


def _running(run: Any) -> ChangeRequest | None:
    if run.iteration == 0:
        return None
    return ChangeRequest.objects.select_for_update().filter(process_run=run).first()


def on_iteration_completed(project: Project, run: Any) -> None:
    """The run completed: its CR is done, and the next queued CR starts by itself.

    The runner keeps a snapshot of the code first, for a CR that starts after the
    workspace is gone (ADR-0018); a CR starting now reuses the live workspace.
    """
    from dexterhouse.apps.workspaces.tasks import snapshot

    project_id = str(project.id)
    transaction.on_commit(lambda: snapshot.delay(project_id), robust=True)
    cr = _running(run)
    if cr is not None and cr.status == CR.RUNNING:
        cr.completed_at = timezone.now()
        set_status(cr, CR.COMPLETED, "completed_at")
        emit(project, "change_request.completed", _payload(cr, iteration=run.iteration))
    try:
        with transaction.atomic():  # a refusal (budget) leaves the CR queued
            start_next_change_request(project, None)
    except DomainError as error:
        logger.warning("projects.change_request_not_started", project_id=str(project.id),
                       reason=error.detail)  # fmt: skip


def on_iteration_failed(project: Project, run: Any, error_code: str | None) -> None:
    cr = _running(run)
    if cr is not None and cr.status == CR.RUNNING:
        set_status(cr, CR.FAILED)
        payload = _payload(cr, iteration=run.iteration, error_code=error_code)
        emit(project, "change_request.failed", payload)


def on_iteration_retried(project: Project, run: Any, user: User) -> None:
    """`failed -> running` of the CR together with the project's *Retry*."""
    cr = _running(run)
    if cr is not None and cr.status == CR.FAILED:
        set_status(cr, CR.RUNNING)
        payload = _payload(cr, iteration=run.iteration, process_run_id=run.id)
        emit(project, "change_request.started", payload, actor=user_actor(user))

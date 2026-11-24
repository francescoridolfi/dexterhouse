# SPDX-License-Identifier: AGPL-3.0-or-later
"""Workspaces seen from the core: request, mirror the runner's state, idle, destroy.

- `request(project)`: a phase with `workspace: true` starts; the row goes `requested`,
  `workspace.requested` is emitted and `runner.workspace.create` is sent after the commit.
  While a workspace is `requested`/`creating` the engine does not advance the project's
  running phases (`pending`).
- `apply_changed(message)`: the runner's callback; emits `workspace.created|error|
  destroyed|resumed`, retries a failed creation (3 attempts, then a `workspace_error`
  escalation) and resumes the engine when the workspace is ready.
- `cleanup()`: beat; `idle` after 15 minutes without tool calls, destroyed when the project
  is archived, completed for 24 h, or inactive for `WORKSPACE_IDLE_DESTROY_H` while not
  running (a running project's workspace holds the only copy of the code until `deliver`).
"""

import json
import time
import uuid
from datetime import timedelta
from typing import Any

import structlog
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from dexterhouse.apps.projects.models import Project, ProjectStatus
from dexterhouse.apps.projects.services.actors import emit
from dexterhouse.apps.workspaces.client import HEARTBEAT_KEY, HEARTBEAT_TTL_S, _redis, get_client
from dexterhouse.apps.workspaces.grants import create_grant
from dexterhouse.apps.workspaces.models import (
    LIVE_STATUSES,
    PENDING_STATUSES,
    Workspace,
    WorkspaceStatus,
)
from dexterhouse_schema.runner import (
    Heartbeat,
    Limits,
    Message,
    Restore,
    Snapshot,
    SnapshotDrop,
    WorkspaceChanged,
    WorkspaceCreate,
    WorkspaceDestroy,
)

logger = structlog.get_logger(__name__)

MAX_ATTEMPTS = 3


def _send(task: str, message: Message) -> None:
    """Send to the runner; with no runner (`LocalRunnerClient`) its reply arrives at once."""
    changed = get_client().send(task, message)
    if changed is not None:
        apply_changed(changed, resume=False)


#: Transitions a callback may make (callbacks can arrive out of order).
_FROM = {
    WorkspaceStatus.CREATING: {WorkspaceStatus.REQUESTED},
    WorkspaceStatus.READY: {
        WorkspaceStatus.REQUESTED,
        WorkspaceStatus.CREATING,
        WorkspaceStatus.IDLE,
        WorkspaceStatus.ERROR,
        WorkspaceStatus.READY,
        WorkspaceStatus.BUSY,
    },
    WorkspaceStatus.ERROR: {
        WorkspaceStatus.REQUESTED,
        WorkspaceStatus.CREATING,
        WorkspaceStatus.READY,
        WorkspaceStatus.IDLE,
        WorkspaceStatus.BUSY,
    },
    WorkspaceStatus.DESTROYED: set(WorkspaceStatus.values) - {WorkspaceStatus.DESTROYED},
}


def limits() -> Limits:
    return Limits(**settings.WORKSPACE_LIMITS)


def for_project(project_id: uuid.UUID) -> Workspace | None:
    return Workspace.objects.filter(project_id=project_id).first()


def live(project_id: uuid.UUID) -> Workspace | None:
    """The project's workspace if it can take tool calls (`ready`, `busy`, `idle`)."""
    return Workspace.objects.filter(project_id=project_id, status__in=LIVE_STATUSES).first()


def pending(project_id: uuid.UUID) -> bool:
    return Workspace.objects.filter(project_id=project_id, status__in=PENDING_STATUSES).exists()


def request(project: Project) -> Workspace:
    """Ask the runner for the project's workspace (idempotent while it lives or is pending)."""
    workspace = Workspace.objects.select_for_update().filter(project=project).first()
    if workspace is not None and workspace.status in (*LIVE_STATUSES, *PENDING_STATUSES):
        return workspace
    stack = dict(project.stack or {})
    if workspace is None:
        workspace = Workspace(project=project)
    workspace.status = WorkspaceStatus.REQUESTED
    workspace.stack = stack
    workspace.image = str(stack.get("workspace_image", ""))
    workspace.attempts = 0
    workspace.error_detail = None
    workspace.destroy_reason = ""
    workspace.save()
    _send_create(project, workspace)
    return workspace


RESTORE_FAILED = "restore from the"


def _restore(project: Project, workspace: Workspace) -> Restore | None:
    """The `restore` of the next creation: the runner's snapshot, or the delivered branch."""
    if workspace.restore_source == "snapshot":
        return Restore(source="snapshot")
    if workspace.restore_source == "remote" and project.remote_repo_url:
        grant = (
            create_grant(project, requested_by_task=f"restore:{workspace.id}")
            if project.remote_token
            else None
        )
        return Restore(
            source="remote",
            remote_url=project.remote_repo_url,
            token_ref=grant.id if grant else None,
            branch=_delivered_branch(project),
        )
    return None


def _delivered_branch(project: Project) -> str:
    """The branch of the last delivery (`main` after a push to main or before any)."""
    from dexterhouse.apps.events.models import Event

    last = (
        Event.objects.filter(project_id=project.id, type="release.delivered")
        .order_by("-created_at")
        .first()
    )
    return ((last.payload or {}).get("branch") if last else None) or "main"


def _create_message(project: Project, workspace: Workspace) -> WorkspaceCreate:
    return WorkspaceCreate(
        project_id=project.id,
        workspace_id=workspace.id,
        stack=workspace.stack,
        limits=limits(),
        restore=_restore(project, workspace),
    )


def _send_create(project: Project, workspace: Workspace) -> None:
    stack = workspace.stack
    emit(
        project,
        "workspace.requested",
        {
            "project_id": project.id,
            "stack": {
                k: str(stack.get(k, "")) for k in ("language", "framework", "workspace_image")
            },
        },
    )
    _send("runner.workspace.create", _create_message(project, workspace))


def retry(project: Project) -> Workspace:
    """Escalation `retry` after three failed creations: start over."""
    with transaction.atomic():
        workspace = Workspace.objects.select_for_update().get(project=project)
        workspace.status = WorkspaceStatus.ERROR
        workspace.save(update_fields=["status", "updated_at"])
        return request(project)


def apply_changed(message: WorkspaceChanged, *, resume: bool = True) -> Workspace | None:
    """`core.runner.workspace_changed`: mirror the state and emit the event."""
    ready = False
    with transaction.atomic():
        workspace = (
            Workspace.objects.select_for_update()
            .select_related("project")
            .filter(pk=message.workspace_id)
            .first()
        )
        if workspace is None:
            logger.warning("workspaces.unknown_workspace", workspace_id=str(message.workspace_id))
            return None
        status = message.status
        if status in _FROM and workspace.status not in _FROM[status]:  # type: ignore[index]
            logger.info(
                "workspaces.stale_callback",
                workspace_id=str(workspace.id),
                current=workspace.status,
                reported=status,
            )
            return workspace
        project = workspace.project
        previous = workspace.status
        if status == WorkspaceStatus.CREATING:
            workspace.status = status
            workspace.save(update_fields=["status", "updated_at"])
        elif status == WorkspaceStatus.READY:
            ready = previous in PENDING_STATUSES or previous == WorkspaceStatus.ERROR
            workspace.status = status
            workspace.image = message.image or workspace.image
            workspace.digest = message.digest or workspace.digest
            workspace.container_id = message.container_id
            workspace.services = list(message.services)
            workspace.volume = f"dh-ws-{workspace.id}"
            workspace.error_detail = None
            if message.restored_commit:
                workspace.restored_commit = message.restored_commit
                workspace.restore_source = ""
            workspace.last_activity_at = timezone.now()
            workspace.save()
            if ready:
                emit(
                    project,
                    "workspace.created",
                    {
                        "workspace_id": workspace.id,
                        "image": workspace.image,
                        "digest": workspace.digest or "",
                        "services": workspace.services,
                        "restored_commit": message.restored_commit,
                    },
                )
            elif previous == WorkspaceStatus.IDLE:
                emit(project, "workspace.resumed", {})
        elif status == WorkspaceStatus.ERROR:
            _failed(project, workspace, message.error_detail or "unknown error")
        elif status == WorkspaceStatus.DESTROYED:
            workspace.status = status
            workspace.container_id = None
            workspace.save(update_fields=["status", "container_id", "updated_at"])
            emit(
                project, "workspace.destroyed", {"reason": workspace.destroy_reason or "completed"}
            )
    if ready and resume:
        resume_engine(workspace.project_id)
    return workspace


def _failed(project: Project, workspace: Workspace, detail: str) -> None:
    workspace.attempts += 1
    workspace.error_detail = detail[:4000]
    emit(project, "workspace.error", {"attempt": workspace.attempts, "error_detail": detail[:2000]})
    retryable = workspace.attempts < MAX_ATTEMPTS and workspace.status in PENDING_STATUSES
    if retryable and workspace.restore_source and detail.startswith(RESTORE_FAILED):
        # Snapshot first, then the delivered branch; nothing else would bring the code back.
        if workspace.restore_source == "snapshot" and project.remote_repo_url:
            workspace.restore_source = "remote"
        else:
            retryable = False
    if retryable:
        workspace.status = WorkspaceStatus.REQUESTED
        workspace.save()
        _send("runner.workspace.create", _create_message(project, workspace))
        return
    workspace.status = WorkspaceStatus.ERROR
    workspace.save()
    transaction.on_commit(lambda: _escalate(project.id, workspace.attempts, detail), robust=True)


def _escalate(project_id: uuid.UUID, attempts: int, detail: str) -> None:
    from dexterhouse.apps.workflows.escalations import escalate
    from dexterhouse.common.errors import InvalidTransitionError

    try:
        escalate(
            project_id,
            "workspace_error",
            {
                "summary": f"The workspace failed {attempts} times: {detail[:300]}",
                "attempts": attempts,
            },
        )
    except InvalidTransitionError as exc:
        logger.warning("workspaces.not_escalated", project_id=str(project_id), reason=str(exc))


def resume_engine(project_id: uuid.UUID) -> None:
    """Advance the project's process once its workspace is ready."""
    from dexterhouse.apps.workflows.engine import common, phases

    with transaction.atomic():
        _project, run = common.lock(project_id)
        if run is not None:
            phases.advance(run)


def prepare_for_iteration(project: Project) -> None:
    """A change request reopens `project` (caller holds the project lock).

    A live workspace still has the code and is reused. A gone one is marked so that the
    next `request` (the first phase with `workspace: true`) restores the last iteration:
    the runner's snapshot, then the delivered branch (ADR-0018). A project that never had
    a workspace has nothing to restore.
    """
    workspace = Workspace.objects.select_for_update().filter(project=project).first()
    if workspace is None or workspace.status in (*LIVE_STATUSES, *PENDING_STATUSES):
        return
    workspace.restore_source = "snapshot"
    workspace.save(update_fields=["restore_source", "updated_at"])


def snapshot(project_id: uuid.UUID) -> str | None:
    """Ask the runner to keep a bundle of the live workspace; returns its commit.

    Called after every completed iteration (`workspaces.tasks.snapshot`). A failure is
    logged: the delivered branch remains the fallback for the next change request.
    """
    workspace = live(project_id)
    if workspace is None:
        return None
    result = get_client().call(
        "runner.system.snapshot", Snapshot(workspace_id=workspace.id, project_id=project_id)
    )
    if not result.ok:
        logger.warning(
            "workspaces.snapshot_failed",
            project_id=str(project_id),
            error=result.error.model_dump() if result.error else None,
        )
        return None
    commit = str((result.data or {}).get("commit") or "")
    Workspace.objects.filter(pk=workspace.pk).update(
        snapshot_commit=commit, snapshot_at=timezone.now()
    )
    return commit or None


def drop_snapshot(project_id: uuid.UUID) -> None:
    """The project is archived: the runner deletes its bundle (idempotent)."""
    result = get_client().call("runner.system.snapshot_drop", SnapshotDrop(project_id=project_id))
    if not result.ok:
        logger.warning("workspaces.snapshot_drop_failed", project_id=str(project_id))


def touch(workspace: Workspace) -> None:
    """A tool call: activity now; an `idle` workspace is `ready` again (`workspace.resumed`)."""
    now = timezone.now()
    if workspace.status == WorkspaceStatus.IDLE:
        updated = Workspace.objects.filter(pk=workspace.pk, status=WorkspaceStatus.IDLE).update(
            status=WorkspaceStatus.READY, last_activity_at=now, updated_at=now
        )
        if updated:
            emit(workspace.project, "workspace.resumed", {})
        return
    Workspace.objects.filter(pk=workspace.pk).update(last_activity_at=now)


def destroy(workspace: Workspace, reason: str) -> None:
    workspace.status = WorkspaceStatus.DESTROYING
    workspace.destroy_reason = reason
    workspace.save(update_fields=["status", "destroy_reason", "updated_at"])
    _send("runner.workspace.destroy", WorkspaceDestroy(workspace_id=workspace.id, reason=reason))


def cleanup(now: Any = None) -> dict[str, int]:
    """Beat: mark quiet workspaces idle, destroy the finished and the abandoned ones."""
    now = now or timezone.now()
    counts = {"idle": 0, "destroyed": 0}
    quiet = Workspace.objects.select_related("project").filter(
        status=WorkspaceStatus.READY,
        last_activity_at__lt=now - timedelta(seconds=settings.WORKSPACE_IDLE_AFTER_S),
    )
    for workspace in quiet:
        with transaction.atomic():
            if Workspace.objects.filter(pk=workspace.pk, status=WorkspaceStatus.READY).update(
                status=WorkspaceStatus.IDLE, updated_at=now
            ):
                emit(workspace.project, "workspace.idle", {})
                counts["idle"] += 1
    inactive_before = now - timedelta(hours=settings.WORKSPACE_IDLE_DESTROY_H)
    for workspace in Workspace.objects.select_related("project").filter(
        status__in=[*LIVE_STATUSES, WorkspaceStatus.ERROR]
    ):
        project = workspace.project
        reason = None
        if project.status == ProjectStatus.ARCHIVED or project.deleted_at is not None:
            reason = "archived"
        elif project.status == ProjectStatus.COMPLETED and (
            project.completed_at is None or project.completed_at < inactive_before
        ):
            reason = "completed"
        elif project.status not in (ProjectStatus.RUNNING, ProjectStatus.WAITING) and (
            (workspace.last_activity_at or workspace.updated_at) < inactive_before
        ):
            reason = "inactive"
        if reason:
            with transaction.atomic():
                destroy(workspace, reason)
            counts["destroyed"] += 1
    return counts


def apply_heartbeat(message: Heartbeat) -> None:
    """`core.runner.heartbeat`: liveness for 45 s; containers the core does not know are orphans."""
    _redis().set(
        f"{HEARTBEAT_KEY}{message.runner_id}",
        json.dumps({**message.model_dump(mode="json"), "sent_at": time.time()}),
        ex=HEARTBEAT_TTL_S,
    )
    known = set(
        Workspace.objects.filter(id__in=message.workspaces)
        .exclude(status=WorkspaceStatus.DESTROYED)
        .values_list("id", flat=True)
    )
    for orphan in set(message.workspaces) - known:
        logger.warning("workspaces.orphan", workspace_id=str(orphan), runner_id=message.runner_id)
        _send("runner.workspace.destroy", WorkspaceDestroy(workspace_id=orphan, reason="orphan"))

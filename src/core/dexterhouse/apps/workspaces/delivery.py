# SPDX-License-Identifier: AGPL-3.0-or-later
"""The `deliver` system action (CD-039, ADR-0016): release branch, pull request, events.

Runs as a Celery task after the `approve_release` gate, so the gate decision does not wait
for the push. Release `<n>` is one more than the releases already delivered. With a token
the core creates a one-time grant (60 s) and sends only its id; the runner redeems it.
`release.delivered` or `release.failed` close the action; nothing is retried on its own.
"""

import uuid

import structlog

from dexterhouse.apps.events.models import Event
from dexterhouse.apps.projects.models import Artifact, ArtifactKind, DeliveryMode, Project
from dexterhouse.apps.projects.services.actors import emit
from dexterhouse.apps.workspaces import services
from dexterhouse.apps.workspaces.client import get_client
from dexterhouse.apps.workspaces.grants import create_grant
from dexterhouse_schema.runner import Deliver, PullRequest

logger = structlog.get_logger(__name__)

FAILURE_CODES = ("auth", "protected_branch", "conflict", "network")


def release_number(project: Project) -> int:
    return Event.objects.filter(project_id=project.id, type="release.delivered").count() + 1


def _notes(project: Project) -> str:
    notes = (
        Artifact.objects.filter(project=project, kind=ArtifactKind.RELEASE_NOTES)
        .order_by("-created_at")
        .first()
    )
    return (notes.content if notes else "")[:60_000]


def deliver(project_id: str | uuid.UUID, phase_run_id: str | uuid.UUID) -> str:
    """Push the release; returns `delivered`, `failed` or `skipped`."""
    project = Project.objects.get(pk=project_id)
    mode = project.delivery_mode
    if not project.remote_repo_url:
        logger.info("workspaces.deliver_skipped", project_id=str(project.id), reason="no remote")
        return "skipped"
    workspace = services.live(project.id)
    if workspace is None:
        emit(
            project,
            "release.failed",
            {
                "mode": mode,
                "error_code": "conflict",
                "detail": "the project has no live workspace to deliver from",
            },
        )
        return "failed"
    n = release_number(project)
    grant = (
        create_grant(project, requested_by_task=f"deliver:{phase_run_id}")
        if project.remote_token
        else None
    )
    message = Deliver(
        workspace_id=workspace.id,
        mode=mode,
        remote_url=project.remote_repo_url,
        token_ref=grant.id if grant else None,
        branch_name=None if mode == DeliveryMode.PUSH_MAIN else f"dexterhouse/release-{n}",
        pr=PullRequest(title=f"{project.name}: release {n}", body=_notes(project))
        if mode == DeliveryMode.PULL_REQUEST
        else None,
    )
    result = get_client().call("runner.system.deliver", message)
    services.touch(workspace)
    if result.ok:
        data = result.data or {}
        emit(
            project,
            "release.delivered",
            {
                "mode": mode,
                "remote_url": project.remote_repo_url,
                "commit": str(data.get("commit", "")),
                "pr_url": data.get("pr_url"),
            },
        )
        logger.info(
            "workspaces.delivered",
            project_id=str(project.id),
            release=n,
            branch=data.get("branch"),
            pr_url=data.get("pr_url"),
        )
        return "delivered"
    code = result.error.code if result.error else "network"
    emit(
        project,
        "release.failed",
        {
            "mode": mode,
            "error_code": code if code in FAILURE_CODES else "network",
            "detail": (result.error.detail if result.error else "")[:2000],
        },
    )
    logger.warning("workspaces.delivery_failed", project_id=str(project.id), code=code)
    return "failed"

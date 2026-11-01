# SPDX-License-Identifier: AGPL-3.0-or-later
"""System actions (actor `system`): workspace, branches, merge, delivery, hiring, exit checks.

Everything that needs the runner is a no-op here that only emits the catalogue events:
E-05 (runner) replaces `workspace_create`, `branch_create`, `merge`, `deliver` and
`check_exit`; E-07 (packages) `install_proposed_packages`. `hire` is real (integration).
"""

import hashlib
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import structlog

from dexterhouse.apps.agents.services.roster import hire_proposed
from dexterhouse.apps.projects.models import Artifact, ArtifactKind, Project
from dexterhouse.apps.projects.services.actors import emit
from dexterhouse.apps.workflows.models import PhaseRun, Task

logger = structlog.get_logger(__name__)
NOOP_DIGEST = "sha256:" + "0" * 64


@dataclass
class ActionResult:
    ok: bool = True
    detail: str | None = None
    data: dict[str, Any] = field(default_factory=dict)


def _fake_commit(*parts: object) -> str:
    return hashlib.sha1(":".join(map(str, parts)).encode(), usedforsecurity=False).hexdigest()


def workspace_create(project: Project, phase_run: PhaseRun) -> ActionResult:
    """No-op (E-05): emits `workspace.requested` and `workspace.created` from `stack`."""
    stack = project.stack
    if not stack:
        return ActionResult(ok=False, detail="the project has no stack")
    emit(
        project,
        "workspace.requested",
        {
            "project_id": project.id,
            "stack": {k: stack[k] for k in ("language", "framework", "workspace_image")},
        },
    )
    workspace_id = uuid.uuid5(project.id, "workspace")
    emit(
        project,
        "workspace.created",
        {
            "workspace_id": workspace_id,
            "image": stack["workspace_image"],
            "digest": NOOP_DIGEST,
            "services": stack.get("services", []),
        },
    )
    return ActionResult(data={"workspace_id": str(workspace_id)})


def branch_create(project: Project, task: Task) -> ActionResult:
    """No-op (E-05): emits `branch.created`."""
    emit(project, "branch.created", {"task_id": task.id, "branch": task.branch})
    return ActionResult()


def merge(project: Project, task: Task) -> ActionResult:
    """No-op (E-05): emits `branch.merged` with a placeholder commit."""
    commit = _fake_commit(task.id, task.iteration)
    emit(
        project,
        "branch.merged",
        {
            "task_id": task.id,
            "branch": task.branch,
            "commit": commit,
            "files_changed": 0,
            "insertions": 0,
            "deletions": 0,
        },
    )
    return ActionResult(data={"commit": commit})


def deliver(project: Project, phase_run: PhaseRun) -> ActionResult:
    """No-op (E-05): emits `release.delivered` when the project has a remote repository."""
    if not project.remote_repo_url:
        logger.info("workflows.deliver_skipped", project_id=str(project.id), reason="no remote")
        return ActionResult(detail="no remote repository")
    emit(
        project,
        "release.delivered",
        {
            "mode": project.delivery_mode,
            "remote_url": project.remote_repo_url,
            "commit": _fake_commit(project.id, phase_run.round),
            "pr_url": None,
        },
    )
    return ActionResult()


def _proposals(project: Project) -> list[dict[str, Any]]:
    latest = (
        Artifact.objects.filter(project=project, kind=ArtifactKind.TEAM_PROPOSAL)
        .order_by("-created_at")
        .first()
    )
    return list(latest.data.get("proposals", [])) if latest and latest.data else []


def install_proposed_packages(project: Project, phase_run: PhaseRun) -> ActionResult:
    """No-op (E-07): records which packages would be installed."""
    names = [f"{p['name']}@{p['version']}" for p in _proposals(project)]
    logger.info("workflows.install_noop", project_id=str(project.id), packages=names)
    return ActionResult(data={"installed": names})


def hire(project: Project, phase_run: PhaseRun) -> ActionResult:
    """Hire one agent per proposal whose package is installed (`agent.hired`).

    The hired roles enable `when: hired`; a proposal whose package is missing (E-07 installs
    from the marketplace) is skipped and logged.
    """
    agents = hire_proposed(project, _proposals(project))
    return ActionResult(
        data={"hired": [a.role for a in agents], "agents": [str(a.id) for a in agents]}
    )


def check_exit(project: Project, exit_kind: str, command: str | None) -> ActionResult:
    """No-op (E-05): `tests_pass` / `command_ok` are reported ok without running anything."""
    return ActionResult(detail=f"{exit_kind} not executed: the runner arrives with E-05")


def merge_all(project: Project, phase_run: PhaseRun) -> ActionResult:
    """No-op (E-05): tasks are already merged one by one when they pass."""
    return ActionResult(detail="nothing to merge")


PHASE_ACTIONS: dict[str, Callable[[Project, PhaseRun], ActionResult]] = {
    "install_proposed_packages": install_proposed_packages,
    "hire": hire,
    "deliver": deliver,
    "merge": merge_all,
}

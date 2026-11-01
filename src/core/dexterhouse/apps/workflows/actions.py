# SPDX-License-Identifier: AGPL-3.0-or-later
"""System actions (actor `system`): workspace, branches, merge, delivery, hiring, exit checks.

The runner actions (E-05) go through `dexterhouse.apps.workspaces`: the workspace is
requested asynchronously (the engine waits while it is `pending`), branches, merges and
exit checks are synchronous runner calls, `deliver` is a Celery task after the gate.
E-07 (packages) replaces `install_proposed_packages`. `hire` is real (integration).
"""

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import structlog
from django.db import transaction

from dexterhouse.apps.agents.services.roster import hire_proposed
from dexterhouse.apps.projects.models import Artifact, ArtifactKind, Project
from dexterhouse.apps.projects.services.actors import emit
from dexterhouse.apps.workflows.models import PhaseRun, Task
from dexterhouse.apps.workspaces import events as workspace_events
from dexterhouse.apps.workspaces import services as workspaces
from dexterhouse.apps.workspaces.client import get_client
from dexterhouse_schema.runner import BranchCreate, ExitCheck, Merge

logger = structlog.get_logger(__name__)
_STACK_VAR = re.compile(r"\$\{stack\.([a-z_]+)\}")


@dataclass
class ActionResult:
    ok: bool = True
    detail: str | None = None
    data: dict[str, Any] = field(default_factory=dict)


def workspace_create(project: Project, phase_run: PhaseRun) -> ActionResult:
    """Request the workspace from `stack`; the phase waits while it is pending."""
    if not project.stack:
        return ActionResult(ok=False, detail="the project has no stack")
    workspace = workspaces.request(project)
    return ActionResult(data={"workspace_id": str(workspace.id), "status": workspace.status})


def workspace_pending(project: Project) -> bool:
    """True while the project's workspace is requested or being created."""
    return workspaces.pending(project.id)


def branch_create(project: Project, task: Task) -> ActionResult:
    """`git checkout -b task/T-xx main` in the workspace, then `branch.created`."""
    workspace = workspaces.live(project.id)
    if workspace is None:
        logger.warning("workflows.branch_without_workspace", task_id=str(task.id))
        return ActionResult(ok=False, detail="no live workspace")
    result = get_client().call(
        "runner.system.branch_create",
        BranchCreate(workspace_id=workspace.id, task_id=task.id, branch=task.branch or ""),
    )
    if not result.ok:
        logger.warning("workflows.branch_failed", task_id=str(task.id), error=str(result.error))
        return ActionResult(ok=False, detail=result.error.detail if result.error else None)
    emit(project, "branch.created", {"task_id": task.id, "branch": task.branch})
    return ActionResult(data=dict(result.data or {}))


def merge(project: Project, task: Task) -> ActionResult:
    """`--no-ff` merge of the task branch into `main`, then `branch.merged`.

    A failed merge (conflict, a secret in uncommitted leftovers) is logged and leaves
    `commit` empty: the task is done by the verdicts, the release shows what was merged.
    """
    workspace = workspaces.live(project.id)
    if workspace is None or not task.branch:
        return ActionResult(ok=False, detail="no live workspace", data={"commit": ""})
    result = get_client().call(
        "runner.system.merge",
        Merge(
            workspace_id=workspace.id,
            task_id=task.id,
            branch=task.branch,
            message=f"merge({task.branch}): {task.title}"[:200],
        ),
    )
    data = dict(result.data or {})
    if not result.ok:
        logger.warning("workflows.merge_failed", task_id=str(task.id), error=str(result.error))
        return ActionResult(
            ok=False, detail=result.error.detail if result.error else None, data={"commit": ""}
        )
    emit(
        project,
        "branch.merged",
        {
            "task_id": task.id,
            "branch": task.branch,
            "commit": str(data.get("commit", "")),
            "files_changed": int(data.get("files_changed", 0)),
            "insertions": int(data.get("insertions", 0)),
            "deletions": int(data.get("deletions", 0)),
        },
    )
    return ActionResult(data={**data, "commit": str(data.get("commit", ""))})


def deliver(project: Project, phase_run: PhaseRun) -> ActionResult:
    """Queue the delivery (`workspaces.tasks.deliver`): push, pull request, `release.*`."""
    if not project.remote_repo_url:
        logger.info("workflows.deliver_skipped", project_id=str(project.id), reason="no remote")
        return ActionResult(detail="no remote repository")
    from dexterhouse.apps.workspaces.tasks import deliver as deliver_task

    project_id, phase_run_id = str(project.id), str(phase_run.id)
    transaction.on_commit(lambda: deliver_task.delay(project_id, phase_run_id), robust=True)
    return ActionResult(detail="delivery queued")


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


def _interpolate(command: str, stack: dict[str, Any]) -> str:
    return _STACK_VAR.sub(lambda m: str(stack.get(m[1]) or ""), command)


def check_exit(project: Project, exit_kind: str, command: str | None) -> ActionResult:
    """`tests_pass` runs `stack.test_command`, `command_ok` the step's command, in the workspace.

    A server command (`${stack.run_command}` with `stack.ports`) is started and probed on
    `http://127.0.0.1:<port><healthcheck_path>`. The output is a `file` artifact and the run
    emits `test.run.started/completed` as `system`. A project without a workspace (a process
    with no `workspace: true` phase) passes, as before E-05.
    """
    stack = dict(project.stack or {})
    if workspaces.for_project(project.id) is None:
        return ActionResult(detail=f"{exit_kind} not executed: the project has no workspace")
    workspace = workspaces.live(project.id)
    if exit_kind == "tests_pass":
        run = str(stack.get("test_command") or "")
    else:
        run = _interpolate(command or "", stack)
    if workspace is None or not run:
        return ActionResult(
            ok=False, detail="no live workspace" if workspace is None else "no command"
        )
    probe = None
    if command and "${stack.run_command}" in command and stack.get("ports"):
        probe = f"http://127.0.0.1:{stack['ports'][0]}{stack.get('healthcheck_path') or '/'}"
    scope = "integration" if exit_kind == "tests_pass" else "smoke"
    emit(project, "test.run.started", {"task_id": None, "scope": scope, "command": run[:300]})
    result = get_client().call(
        "runner.system.exit_check",
        ExitCheck(
            workspace_id=workspace.id, kind=exit_kind, command=run, timeout_s=900, probe_url=probe
        ),
        timeout_s=900,
    )
    workspaces.touch(workspace)
    report = workspace_events.output_artifact(
        project,
        f"test_runs/exit-{exit_kind}.log",
        result.artifact_payload or str((result.data or {}).get("detail") or ""),
        role="system",
    )
    workspace_events.run_completed(project, result, report, scope=scope)
    data = result.data or {}
    detail = data.get("detail") or (result.error.detail if result.error else None)
    if not result.ok and not detail:
        detail = f"exit code {result.exit_code}: {str(data.get('tail', ''))[-300:]}"
    return ActionResult(ok=result.ok, detail=detail, data={"report_artifact": str(report.id)})


def merge_all(project: Project, phase_run: PhaseRun) -> ActionResult:
    """Nothing to do: each task is merged into `main` when it passes (`merge`)."""
    return ActionResult(detail="nothing to merge")


PHASE_ACTIONS: dict[str, Callable[[Project, PhaseRun], ActionResult]] = {
    "install_proposed_packages": install_proposed_packages,
    "hire": hire,
    "deliver": deliver,
    "merge": merge_all,
}

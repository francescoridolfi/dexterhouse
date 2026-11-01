# SPDX-License-Identifier: AGPL-3.0-or-later
"""Events the core derives from runner results (contracts/events/workspace_release.md).

`commit.created` and `test.run.*` are the agent's (actor agent); the exit checks of the
engine re-run the tests as `system`. Full outputs past 64 KB and test reports become
`file` artifacts (`tool_outputs/…`, `test_runs/…`) referenced from the results.
"""

import uuid
from typing import Any

import structlog

from dexterhouse.apps.agents.models import AgentTurn
from dexterhouse.apps.agents.services.events import emit_turn
from dexterhouse.apps.projects.models import Artifact, ArtifactKind, Project
from dexterhouse.apps.projects.services.actors import emit
from dexterhouse.apps.projects.services.artifacts import save_artifact
from dexterhouse_schema.runner import SecretsBlocked, ToolResult

logger = structlog.get_logger(__name__)
ARTIFACT_LIMIT = 4 * 1024 * 1024


def output_artifact(
    project: Project,
    name: str,
    content: str,
    *,
    turn: AgentTurn | None = None,
    phase_run_id: uuid.UUID | None = None,
    role: str = "",
) -> Artifact:
    return save_artifact(
        project,
        kind=ArtifactKind.FILE,
        name=name,
        content=content[:ARTIFACT_LIMIT],
        phase_run_id=phase_run_id or (turn.phase_run_id if turn else None),
        turn_id=turn.id if turn else None,
        role=role or (turn.agent_instance.role if turn else ""),
    )


def secrets_blocked(message: SecretsBlocked) -> None:
    turn = AgentTurn.objects.select_related("agent_instance").filter(pk=message.turn_id).first()
    if turn is None or turn.task_id is None:
        logger.warning(
            "workspaces.secrets_blocked_without_task",
            turn_id=str(message.turn_id),
            files=message.files,
        )
        return
    emit_turn(
        turn,
        "secrets.blocked",
        {"task_id": turn.task_id, "files": message.files, "count": message.count},
        system=True,
    )


def commit_created(turn: AgentTurn, result: ToolResult) -> None:
    data = result.data or {}
    if turn.task_id is None or not data.get("commit"):
        return
    emit_turn(
        turn,
        "commit.created",
        {
            "task_id": turn.task_id,
            "branch": str(data.get("branch", "")),
            "commit": str(data["commit"]),
            "message": str(data.get("message", ""))[:500],
            "files_changed": int(data.get("files_changed", 0)),
        },
    )


def run_scope(turn: AgentTurn | None) -> str:
    if turn is not None and turn.task_id is not None:
        return "task"
    return "smoke" if turn is not None and turn.step == "smoke" else "integration"


def run_started(turn: AgentTurn, command: str) -> None:
    emit_turn(
        turn,
        "test.run.started",
        {
            "task_id": turn.task_id,
            "scope": run_scope(turn),
            "command": command[:300],
        },
    )


def run_completed(
    project: Project,
    result: ToolResult,
    report: Artifact,
    *,
    turn: AgentTurn | None = None,
    scope: str | None = None,
) -> dict[str, Any]:
    data = result.data or {}
    summary = data.get("summary") or {}
    payload = {
        "task_id": turn.task_id if turn else None,
        "scope": scope or run_scope(turn),
        "passed": int(summary.get("passed", 0)),
        "failed": int(summary.get("failed", 0)),
        "skipped": int(summary.get("skipped", 0)),
        "duration_s": round(result.duration_ms / 1000, 3),
        "ok": bool(result.ok and data.get("ok", result.exit_code == 0)),
        "report_artifact": {"id": report.id, "version": report.version},
    }
    if turn is not None:
        emit_turn(turn, "test.run.completed", payload)
    else:
        emit(project, "test.run.completed", payload)
    return payload

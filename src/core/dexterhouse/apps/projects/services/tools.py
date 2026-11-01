# SPDX-License-Identifier: AGPL-3.0-or-later
"""The `project.*` and `skills.read` tools (contracts/tools/memory.md), as plain services.

`dexterhouse.apps.projects.mcp_server` exposes them over MCP to one turn: every call runs
for the project and the turn the core started the server for, never another one. Which
agent may call which tool is decided before the call, by the tool gateway (`allowed_tools`).
"""

import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from django.conf import settings
from django.db import transaction
from django.db.models import Max

from dexterhouse.apps.agents.models import AgentTurn
from dexterhouse.apps.agents.schemas import TurnInputs
from dexterhouse.apps.projects.models import Artifact, Note
from dexterhouse.apps.projects.services import notes as notes_service
from dexterhouse.apps.workflows.models import Task

RESULT_LIMIT = 64 * 1024
_HEADING = re.compile(r"^## +(.+?)\s*$", re.MULTILINE)


class ToolError(ValueError):
    """A refused or invalid call; the message goes back to the agent."""


@dataclass(frozen=True)
class ToolContext:
    project_id: uuid.UUID
    turn_id: uuid.UUID

    def turn(self) -> AgentTurn:
        turn = (
            AgentTurn.objects.select_related("agent_instance")
            .filter(pk=self.turn_id, project_id=self.project_id)
            .first()
        )
        if turn is None:
            raise ToolError("unknown turn for this project")
        return turn


# project.artifact / project.artifacts ----------------------------------------------------


def artifact(
    ctx: ToolContext,
    kind: str,
    name: str | None = None,
    version: int | str = "latest",
    section: str | None = None,
) -> dict[str, Any]:
    """One artifact version; past 64 KB only its `##` sections are listed (ask by section)."""
    rows = Artifact.objects.filter(project_id=ctx.project_id, kind=kind)
    if name:
        rows = rows.filter(name=name)
    if version != "latest":
        rows = rows.filter(version=int(version))
    found = rows.order_by("-created_at").first()
    if found is None:
        raise ToolError(f"no {kind} artifact" + (f" named {name}" if name else ""))
    result: dict[str, Any] = {
        "id": str(found.id),
        "kind": found.kind,
        "name": found.name,
        "version": found.version,
    }
    if found.data is not None:
        return result | {"data": found.data}
    content = found.content
    if section:
        content = _section(content, section)
    if len(content.encode("utf-8")) > RESULT_LIMIT:
        return result | {"truncated": True, "sections": _HEADING.findall(content)}
    return result | {"content": content}


def _section(content: str, title: str) -> str:
    parts = _HEADING.split(content)
    for index in range(1, len(parts), 2):
        if parts[index].strip().lower() == title.strip().lower():
            return f"## {parts[index]}{parts[index + 1]}"
    raise ToolError(f"no section {title!r}; sections: {', '.join(parts[1::2])}")


def artifacts(ctx: ToolContext, kind: str | None = None) -> dict[str, Any]:
    """The latest version of every artifact (kind, name, version, size, produced_by)."""
    rows = Artifact.objects.filter(project_id=ctx.project_id)
    if kind:
        rows = rows.filter(kind=kind)
    latest = rows.values("kind", "name").annotate(v=Max("version"))
    wanted = {(r["kind"], r["name"], r["v"]) for r in latest}
    items = [
        {
            "id": str(a.id),
            "kind": a.kind,
            "name": a.name,
            "version": a.version,
            "size": len(a.content.encode("utf-8")) if a.data is None else None,
            "produced_by": a.produced_by_role or "user",
        }
        for a in rows.order_by("kind", "name")
        if (a.kind, a.name, a.version) in wanted
    ]
    return {"artifacts": items}


# project.tasks / project.notes -----------------------------------------------------------


def tasks(ctx: ToolContext, status: str | None = None) -> dict[str, Any]:
    """The task board: top-level tasks with state and iterations."""
    rows = Task.objects.filter(project_id=ctx.project_id, parent__isnull=True)
    if status:
        rows = rows.filter(status=status)
    by_id = dict(Task.objects.filter(project_id=ctx.project_id).values_list("id", "external_id"))
    return {
        "tasks": [
            {
                "external_id": t.external_id,
                "kind": t.kind,
                "title": t.title,
                "status": t.status,
                "iteration": t.iteration,
                "max_iterations": t.max_iterations,
                "assigned_role": t.assigned_role,
                "depends_on": [by_id.get(d) for d in t.depends_on],
                "current_step": t.current_step,
                "branch": t.branch,
            }
            for t in rows.order_by("order")
        ]
    }


def notes(ctx: ToolContext, unconsumed_only: bool = True) -> dict[str, Any]:
    """The user's notes for this phase; marks them consumed by the turn (not idempotent)."""
    turn = ctx.turn()
    rows = Note.objects.filter(project_id=ctx.project_id, phase_run__isnull=True) | (
        Note.objects.filter(project_id=ctx.project_id, phase_run_id=turn.phase_run_id)
    )
    with transaction.atomic():
        selected = [
            n
            for n in rows.select_for_update().order_by("-created_at")
            if not (unconsumed_only and n.consumed_by_turn_ids)
        ]
        agent = turn.agent_instance
        notes_service.consume(
            agent.project, [n.id for n in selected], turn.id, agent.id, agent.role
        )
    return {
        "notes": [
            {"id": str(n.id), "content": n.content, "created_at": n.created_at.isoformat()}
            for n in selected
        ]
    }


# project.ask -----------------------------------------------------------------------------


def ask(ctx: ToolContext, questions: list[dict[str, Any]]) -> dict[str, Any]:
    """Questions for the human. The engine opens the `question` gate when the turn ends.

    Supervised: the agent ends the turn with `status: waiting_answers` and a `questions`
    artifact; the answers arrive in the next turn. Autonomous: `mode: assume`, the agent
    writes `assumptions` and goes on.
    """
    if not questions or any(not q.get("id") or not q.get("text") for q in questions):
        raise ToolError("questions must be a non-empty list of {id, text, kind, options?}")
    inputs = TurnInputs.model_validate(ctx.turn().inputs)
    if not inputs.may_ask:
        raise ToolError("this step may not ask questions: state assumptions instead")
    if inputs.mode == "autonomous":
        return {
            "mode": "assume",
            "instructions": "Do not wait for answers: write an `assumptions` artifact with "
            "your default assumptions, list them in assumptions_made and complete the step.",
        }
    return {
        "mode": "ask",
        "questions": len(questions),
        "instructions": "End the turn now with status `waiting_answers` and a `questions` "
        "artifact holding these questions; the answers arrive in your next turn.",
    }


# skills.read -----------------------------------------------------------------------------


def builtin_skills_dir() -> Path:
    return Path(settings.BUILTIN_DIR) / "skills"


def read_skill(ctx: ToolContext, name: str, path: str = "SKILL.md") -> dict[str, Any]:
    """A skill of the agent's package (or a built-in one); emits `agent.skill.loaded`."""
    from dexterhouse.apps.agents.services.events import emit_turn
    from dexterhouse.apps.agents.services.packages import PackageError, load_agent_package

    turn = ctx.turn()
    agent = turn.agent_instance
    roots = []
    if agent.package_path:
        try:
            package = load_agent_package(agent.package_path)
        except PackageError as exc:
            raise ToolError(str(exc)) from exc
        if name in package.agent.skills:
            roots.append(package.root / "skills" / name)
    roots.append(builtin_skills_dir() / name)
    root = next((r.resolve() for r in roots if (r / "SKILL.md").is_file()), None)
    if root is None:
        raise ToolError(f"unknown skill {name!r}")
    target = (root / path).resolve()
    if not target.is_relative_to(root) or not target.is_file():
        raise ToolError(f"{path!r} is not a file of the skill {name!r}")
    content = target.read_text(encoding="utf-8")[:RESULT_LIMIT]
    if path == "SKILL.md":
        with transaction.atomic():
            emit_turn(
                turn,
                "agent.skill.loaded",
                {"turn_id": str(turn.id), "agent_id": str(agent.id), "skill": name},
            )
    return {"name": name, "path": path, "content": content}

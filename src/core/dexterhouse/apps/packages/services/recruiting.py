# SPDX-License-Identifier: AGPL-3.0-or-later
"""The `packages.*` tools of the Recruiter (contracts/tools/marketplace.md), as services.

`packages.propose` stores nothing of its own: the proposals of a turn are the arguments
of its `packages.propose` calls, kept by the tool gateway in `ToolCall` (one row per call,
idempotent per turn and sequence). The tool checks each entry against the registry index
and the task board and answers with the index data the `team_proposal` artifact must copy;
that artifact remains what the `approve_plan` gate shows and `install_proposed_packages`
consumes. `packages.install` exists only in `autonomous` mode (the agents runtime leaves it
out of supervised turns, and the server checks the mode again) and installs only verified
packages whose risk is low; anything else answers `requires_gate`.
"""

import uuid
from dataclasses import dataclass
from typing import Any

from dexterhouse.apps.packages.services import catalog, installer, marketplace
from dexterhouse.apps.packages.services import index as registry
from dexterhouse.apps.projects.models import Artifact, ExecutionMode, Project
from dexterhouse.apps.projects.services.tools import ToolError
from dexterhouse_schema.artifacts.team_proposal import MAX_PROPOSALS

KINDS = ("agent", "tool", "process")


@dataclass(frozen=True)
class RecruitingContext:
    project_id: uuid.UUID
    organization_id: uuid.UUID

    def project(self) -> Project:
        project = Project.objects.filter(
            pk=self.project_id, organization_id=self.organization_id
        ).first()
        if project is None:
            raise ToolError("unknown project")
        return project


def installed(ctx: RecruitingContext, kind: str | None = None) -> dict[str, Any]:
    """Packages the organization has, with the enabled version and status."""
    if kind is not None and kind not in KINDS:
        raise ToolError(f"kind must be one of {', '.join(KINDS)}")
    rows = catalog.visible_packages(ctx.organization_id).select_related("enabled_version")
    if kind:
        rows = rows.filter(kind=kind)
    packages = []
    for package in rows.order_by("kind", "name"):
        enabled = package.enabled_version
        definition = enabled.definition if enabled else {}
        packages.append(
            {
                "name": package.name,
                "kind": package.kind,
                "version": enabled.version if enabled else None,
                "status": package.status,
                "source": package.source,
                "role": definition.get("role") if package.kind == "agent" else None,
            }
        )
    return {"packages": packages}


def _task_ids(project_id: uuid.UUID) -> set[str]:
    board = (
        Artifact.objects.filter(project_id=project_id, kind="task_board")
        .order_by("-created_at")
        .first()
    )
    tasks = (board.data or {}).get("tasks", []) if board else []
    return {str(t.get("external_id")) for t in tasks}


def _check(entry: Any, wanted: dict[str, Any], task_ids: set[str]) -> tuple[Any, list[str]]:
    problems: list[str] = []
    if entry is None:
        return None, ["not in the registry index"]
    if entry.kind != "agent":
        problems.append(f"kind {entry.kind}: only agent packages are proposed")
    if entry.risk == "high":
        problems.append("risk high: cannot be proposed")
    chosen = registry.pick_version(entry, str(wanted.get("version") or "") or None)
    if chosen is None:
        problems.append("no such version compatible with this core")
    elif not registry.compatible(chosen.compat_core):
        problems.append(f"{chosen.version} is not compatible with this core")
    for_tasks = [str(t) for t in wanted.get("for_tasks") or []]
    if not for_tasks:
        problems.append("for_tasks is empty")
    elif unknown := sorted(set(for_tasks) - task_ids):
        problems.append(f"for_tasks not in the task board: {', '.join(unknown)}")
    if not str(wanted.get("reason") or "").strip():
        problems.append("reason is empty")
    return chosen, problems


def propose(ctx: RecruitingContext, proposals: list[dict[str, Any]]) -> dict[str, Any]:
    """Check the proposals of the turn; returns the accepted ones with their index data."""
    if not isinstance(proposals, list) or not proposals:
        raise ToolError("proposals must be a non-empty list of {name, version, reason, for_tasks}")
    if len(proposals) > MAX_PROPOSALS:
        raise ToolError(f"at most {MAX_PROPOSALS} proposals")
    task_ids = _task_ids(ctx.project_id)
    recorded, rejected = [], []
    for wanted in proposals:
        name = str(wanted.get("name") or "")
        entry = marketplace.entry(name)
        chosen, problems = _check(entry, wanted, task_ids)
        if problems:
            rejected.append({"name": name, "problems": problems})
            continue
        recorded.append(
            {
                "name": entry.name,
                "version": chosen.version,
                "reason": str(wanted["reason"]),
                "for_tasks": [str(t) for t in wanted["for_tasks"]],
                "verified": entry.verified,
                "risk": entry.risk,
                "author_github": entry.author_github,
                "rating": None,
                "installs": None,
            }
        )
    return {
        "recorded": recorded,
        "rejected": rejected,
        "note": "Recorded for this turn only; copy them into team_proposal.json. "
        "role and permissions come from marketplace.details.",
    }


def install(ctx: RecruitingContext, name: str, version: str = "") -> dict[str, Any]:
    """Autonomous mode only: install a verified, low-risk package for the project."""
    project = ctx.project()
    if project.execution_mode != ExecutionMode.AUTONOMOUS:
        raise ToolError("requires_gate: packages are installed after approve_plan in supervised")
    entry = marketplace.entry(name)
    if entry is None:
        raise ToolError(f"{name} is not in the registry index (or the registry is unreachable)")
    if not entry.verified or entry.risk != "low" or entry.kind == "process":
        raise ToolError(
            f"requires_gate: {name} is {'verified' if entry.verified else 'not verified'} "
            f"with risk {entry.risk}; only verified low-risk agents and tools install "
            "autonomously, propose it instead"
        )
    result = installer.install(
        organization=project.organization, source=name, version=version, project=project
    )
    installed_version = result.package_version.version if result.package_version else version
    return {
        "name": name,
        "version": installed_version or None,
        "status": result.status,
        "install_id": str(result.id),
        "errors": list(result.errors or []),
    }

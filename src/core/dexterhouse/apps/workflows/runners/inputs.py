# SPDX-License-Identifier: AGPL-3.0-or-later
"""`TurnRequest` -> `TurnInputs`: what a turn reads, per agents/handoffs.md.

Processes do not declare the input artifacts of a step yet, so the defaults below follow
the hand-off table and the built-in prompts (E-04): each step reads the latest version of
the kinds listed for it (first match of `<phase>:<step>`, `<step>`, `<role>`), in priority
order. A reopened phase (round > 0) also reads its own previous outputs. Inside a loop,
`dev_notes`, `review` and `test_report` are limited to the current task; outside, the
task-level test reports are left out. The step description tells the agent what this
step wants from it (`STEP` guides) plus what the core knows that no artifact holds:
installed roles, the team, the last finding id, the project summary.
"""

import re
from typing import Any

from django.db.models import Count, Max, Sum

from dexterhouse.apps.agents.models import AgentInstance, AgentStatus, AgentTurn
from dexterhouse.apps.agents.schemas import ArtifactInput, NoteInput, TaskInput, TurnInputs
from dexterhouse.apps.projects.models import Artifact, Note, Project
from dexterhouse.apps.workflows.models import Gate, StepRun, Task
from dexterhouse.apps.workflows.roles import BUILTIN_ROLES, installed_roles
from dexterhouse.apps.workflows.runner import TurnRequest

DEFAULT_INPUTS: dict[str, tuple[str, ...]] = {
    "analyst": ("brief", "questions", "requirements", "user_stories", "assumptions"),
    "architect": ("requirements", "user_stories"),
    "project_manager": ("architecture", "stack", "requirements", "user_stories"),
    "recruiter": ("task_board", "stack", "architecture", "brief"),
    "replan": ("task_board", "team_proposal"),
    "developer": ("stack", "architecture", "dev_notes", "task_board"),
    "reviewer": ("dev_notes", "review", "stack", "architecture"),
    "tester": ("review", "test_report", "stack", "dev_notes"),
    "integration_test": ("task_board", "stack"),
    "smoke": ("stack",),
    "release:project_manager": ("test_report", "task_board", "assumptions", "stack"),
    "retrospective:project_manager": ("release_notes", "task_board", "test_report", "assumptions"),
}
TASK_KINDS = frozenset({"dev_notes", "review", "test_report"})
WORKSPACE_IMAGES = (
    "dexterhouse/workspace:python (Python 3.12, uv, pip), "
    "dexterhouse/workspace:node (Node 22, npm, pnpm), "
    "dexterhouse/workspace:full (Python 3.12, Node 22, Go); services: postgres, redis, mailpit"
)
_FINDING = re.compile(r"^R-(\d+)$")


def _key(request: TurnRequest, table: dict[str, Any]) -> str | None:
    keys = (f"{request.phase_id}:{request.step}", request.step, request.role)
    return next((k for k in keys if k in table), None)


def input_kinds(request: TurnRequest) -> tuple[str, ...]:
    key = _key(request, DEFAULT_INPUTS)
    kinds = DEFAULT_INPUTS[key] if key else ()
    if request.round > 0:  # sent back by a gate: the agent revises its own outputs
        kinds = (*kinds, *(k for k in request.produces if k not in kinds))
    return kinds


def _latest(project_id: Any, kinds: tuple[str, ...], task_ref: str | None) -> list[Artifact]:
    """Latest version of every (kind, name) of `kinds`, in the order of `kinds`."""
    rows = Artifact.objects.filter(project_id=project_id, kind__in=kinds)
    latest = rows.values("kind", "name").annotate(v=Max("version"))
    wanted = {(r["kind"], r["name"], r["v"]) for r in latest}
    artifacts = [a for a in rows.order_by("created_at") if (a.kind, a.name, a.version) in wanted]
    if task_ref:
        artifacts = [a for a in artifacts if a.kind not in TASK_KINDS or task_ref in a.name]
    else:
        artifacts = [a for a in artifacts if not _task_report(a)]
    return sorted(artifacts, key=lambda a: kinds.index(a.kind))


def _task_report(artifact: Artifact) -> bool:
    return artifact.kind == "test_report" and (artifact.data or {}).get("scope") == "task"


def _artifact_input(artifact: Artifact) -> ArtifactInput:
    return ArtifactInput(
        id=artifact.id,
        kind=artifact.kind,
        name=artifact.name,
        version=artifact.version,
        content=artifact.content if artifact.data is None else None,
        data=artifact.data,
    )


def _task_reports(project_id: Any, task_ref: str, kind: str) -> list[Artifact]:
    rows = Artifact.objects.filter(project_id=project_id, kind=kind, name__contains=task_ref)
    return list(rows.order_by("created_at"))


def review_context(project_id: Any, task_ref: str) -> tuple[list[dict[str, Any]], list[str]]:
    """Open findings and failures of the task's latest review/test, and every finding id."""
    reviews = _task_reports(project_id, task_ref, "review")
    tests = _task_reports(project_id, task_ref, "test_report")
    known = sorted({f["id"] for r in reviews for f in (r.data or {}).get("findings", [])})
    items: list[dict[str, Any]] = []
    if reviews:
        items += [f for f in reviews[-1].data.get("findings", []) if not f.get("resolved")]
    if tests and tests[-1].data.get("verdict") == "fail":
        items += tests[-1].data.get("failures", [])
    return items, known


def _team(project_id: Any) -> list[AgentInstance]:
    hired = AgentInstance.objects.filter(project_id=project_id).exclude(status=AgentStatus.RELEASED)
    return list(hired.order_by("hired_at"))


def _roles(project_id: Any) -> list[str]:
    org = Project.objects.filter(id=project_id).values_list("organization_id", flat=True).first()
    return sorted(installed_roles(org) | {a.role for a in _team(project_id)})


def _board(project_id: Any) -> dict[str, Any] | None:
    board = Artifact.objects.filter(project_id=project_id, kind="task_board")
    latest = board.order_by("-created_at").first()
    return latest.data if latest is not None and latest.data else None


def _task_ids(project_id: Any) -> list[str] | None:
    """Task ids of the latest board and of the tasks created from it (proposal checks)."""
    ids = set(
        Task.objects.filter(project_id=project_id, parent__isnull=True).values_list(
            "external_id", flat=True
        )
    )
    board = _board(project_id)
    if board is not None:
        ids |= {t["external_id"] for t in board.get("tasks", [])}
    return sorted(ids) or None


def _files_hint(project_id: Any, task_ref: str) -> list[str]:
    board = _board(project_id) or {}
    task = next((t for t in board.get("tasks", []) if t["external_id"] == task_ref), {})
    return list(task.get("files_hint", []))


def build_inputs(request: TurnRequest, step_run: StepRun) -> TurnInputs:
    project = step_run.project
    task = request.task
    task_ref = task.external_id if task else None
    artifacts = _latest(project.id, input_kinds(request), task_ref)
    notes = Note.objects.filter(project=project, phase_run__isnull=True) | Note.objects.filter(
        project=project, phase_run=step_run.phase_run_id
    )
    answers = [f"{a.question_id}: {a.answer}" for a in request.answers]
    if request.comment:
        answers.insert(0, f"Gate comment: {request.comment}")
    items: list[dict[str, Any]] = []
    known: list[str] | None = None
    if task_ref:
        items, known_ids = review_context(project.id, task_ref)
        known = known_ids if request.verdict_rule == "review" else None
        if request.verdict_rule != "none":
            items = []  # reviewers and testers judge the new iteration, not the old findings
    stack = project.stack or {}
    return TurnInputs(
        step_description=describe(request, project.id, stack, known),
        produces=list(request.produces),
        task=TaskInput(
            external_id=task.external_id,
            title=task.title,
            description=task.description,
            acceptance=task.acceptance,
            iteration=task.iteration,
            max_iterations=task.max_iterations,
            files_hint=_files_hint(project.id, task.external_id),
        )
        if task
        else None,
        gate_answers=answers,
        review_items=items,
        artifacts=[_artifact_input(a) for a in artifacts],
        notes=[NoteInput(id=n.id, text=n.content) for n in notes.order_by("-created_at")],
        room=step_run.phase_run.room or None,
        mode=request.execution_mode,
        may_ask=request.may_ask,
        data_residency=project.data_residency,
        verdict_rule=request.verdict_rule,
        known_finding_ids=known,
        installed_roles=_roles(project.id),
        task_ids=_task_ids(project.id),
        stack_test_command=stack.get("test_command"),
        workspace_tree=workspace_tree(project.id),
    )


# Step description ---------------------------------------------------------------------


def describe(
    request: TurnRequest, project_id: Any, stack: dict[str, Any], known: list[str] | None
) -> str:
    """Process position, what to produce, and the step's guide (`STEP`)."""
    lines = [
        f"Process {request.process}, phase `{request.phase_id}`, step `{request.step}` "
        f"(role {request.role}, round {request.round}, {request.execution_mode} mode)."
    ]
    if request.produces:
        lines.append(f"Produce these artifacts: {', '.join(request.produces)}.")
    if request.verdict_rule != "none":
        lines.append(f"Give a `{request.verdict_rule}` verdict.")
    if request.task and request.task.branch:
        lines.append(f"Work on branch `{request.task.branch}`.")
    key = _key(request, STEP)
    if key is not None:
        lines += STEP[key](request, project_id, stack, known)
    return "\n".join(line for line in lines if line)


def _analyst(request: TurnRequest, *_: Any) -> list[str]:
    if request.answers:
        return [
            "The human answered your questions (below, `id: answer`). Write the final "
            "requirements.md and user_stories.md without the DRAFT marker, record every answer "
            "in Open points and in the Changelog, and ask nothing new."
        ]
    lines = []
    if request.comment:
        lines.append(
            "A human gate sent your work back with the comment below: address every point "
            "in the Changelog and in the body; keep ids stable."
        )
    if not request.may_ask:
        lines.append("Questions are not allowed in this step: write assumptions instead.")
    elif request.execution_mode == "autonomous":
        lines.append(
            "Autonomous mode: nobody answers questions. project.ask replies `mode: assume`: "
            "write an assumptions artifact (assumptions.json) for every decision you had to "
            "take and list them in assumptions_made."
        )
    elif not request.comment:
        lines.append(
            "You may ask the human: if answers would materially change the requirements, call "
            "project.ask (at most 6 questions) and end with status waiting_answers, the "
            "questions artifact (questions.json) and DRAFT requirements and stories. Otherwise "
            "write assumptions."
        )
    return lines


def _architect(*_: Any) -> list[str]:
    return [f"Supported workspace images: {WORKSPACE_IMAGES}."]


def _planning(request: TurnRequest, project_id: Any, *_: Any) -> list[str]:
    return [
        f"Installed roles you may assign: {', '.join(_roles(project_id))}.",
        "Write task_board.json; T-01 is the repository scaffold.",
    ]


def _roster(project_id: Any) -> str:
    team = _team(project_id)
    return ", ".join(f"{a.role} ({a.package_name}@{a.package_version})" for a in team) or "none"


def _recruiter(request: TurnRequest, project_id: Any, *_: Any) -> list[str]:
    install = (
        "you may install verified packages whose risk is low with packages.install"
        if request.execution_mode == "autonomous"
        else "you only propose: installation happens after the approve_plan gate"
    )
    return [
        f"Current team: {_roster(project_id)}.",
        f"Execution mode {request.execution_mode}: {install}.",
        "Write team_proposal.json; task ids must come from the task board.",
    ]


def _replan(request: TurnRequest, project_id: Any, *_: Any) -> list[str]:
    hired = sorted({a.role for a in _team(project_id)} - BUILTIN_ROLES)
    return [
        f"Current team: {_roster(project_id)}.",
        f"Newly hired roles: {', '.join(hired) or 'none'}. Assign them the tasks of the "
        "accepted team_proposal (`for_tasks`); change only assigned_role or split tasks, keep "
        "ids and approved descriptions; publish task_board.json again.",
    ]


def _developer(request: TurnRequest, *_: Any) -> list[str]:
    task = request.task
    if task is None:
        return []
    lines = [
        f"Write dev_notes/{task.external_id}-iter{task.iteration}.md and commit with messages "
        f"scoped to {task.external_id}; tests/acceptance/ belongs to the tester."
    ]
    if task.iteration > 1:
        lines.append(
            "Fix iteration: the open findings or failing tests are listed below; answer each "
            "one in the Responses section."
        )
    return lines


def _reviewer(
    request: TurnRequest, project_id: Any, stack: dict[str, Any], known: list[str] | None
) -> list[str]:
    task = request.task
    if task is None:
        iteration = request.round + 1
        return [
            "Repository review (no task): review the whole repository, use task_id `T-00`, "
            f"iteration {iteration} and name reviews/repository-iter{iteration}.md."
        ]
    numbers = [int(m[1]) for f in known or [] if (m := _FINDING.match(f))]
    last = f"R-{max(numbers)}" if numbers else "none (start at R-1)"
    return [
        f"Write reviews/{task.external_id}-iter{task.iteration}.md with task_id "
        f"{task.external_id} and iteration {task.iteration}. Last finding id used for this "
        f"task: {last}; your previous reviews of the task are below."
    ]


def _tester(request: TurnRequest, *_: Any) -> list[str]:
    task = request.task
    if task is None:
        return []
    return [
        f"Write acceptance tests under tests/acceptance/ and test_reports/{task.external_id}-"
        f"iter{task.iteration}.json with scope task, task_id {task.external_id} and iteration "
        f"{task.iteration}."
    ]


def _integration(
    request: TurnRequest, project_id: Any, stack: dict[str, Any], *_: Any
) -> list[str]:
    command = stack.get("test_command", "the stack's test_command")
    return [
        f"Run the whole suite: test_reports/integration_test.json with scope integration and "
        f"command exactly `{command}`."
    ]


def _smoke(request: TurnRequest, project_id: Any, stack: dict[str, Any], *_: Any) -> list[str]:
    port = (stack.get("ports") or ["the declared port"])[0]
    path = stack.get("healthcheck_path") or "/"
    return [
        f"Smoke test: start `{stack.get('run_command', 'run_command')}`, request "
        f"http://localhost:{port}{path}, then write test_reports/smoke.json with scope smoke "
        "and the smoke block."
    ]


def _release(request: TurnRequest, project_id: Any, *_: Any) -> list[str]:
    commits = commit_log(project_id)
    if not commits:
        return [
            "Write release_notes.md from the test reports, task board, assumptions and stack "
            "below. No commit log is available: say so under Commits."
        ]
    return [
        "Write release_notes.md from the test reports, task board, assumptions and stack "
        f"below; under Commits summarise these {len(commits)} commits of main (newest first):",
        *(f"- {c['commit'][:8]} {c['message']} ({c['author']})" for c in commits),
    ]


# Workspace (E-05) -----------------------------------------------------------------------


def _runner(task: str, message: Any) -> dict[str, Any] | None:
    from dexterhouse.apps.workspaces.client import get_client

    result = get_client().call(task, message)
    return result.data if result.ok and isinstance(result.data, dict) else None


def workspace_tree(project_id: Any) -> str | None:
    """The live workspace's file tree (depth 3) for the context builder, else None."""
    from dexterhouse.apps.workspaces.services import live
    from dexterhouse_schema.runner import Tree

    workspace = live(project_id)
    if workspace is None:
        return None
    data = _runner("runner.system.tree", Tree(workspace_id=workspace.id, depth=3))
    return str(data["tree"]) if data and data.get("tree") else None


def commit_log(project_id: Any, limit: int = 60) -> list[dict[str, str]]:
    """Commits of `main` in the workspace, for the PM's release notes."""
    from dexterhouse.apps.workspaces.services import live
    from dexterhouse_schema.runner import CommitLog

    workspace = live(project_id)
    if workspace is None:
        return []
    data = _runner("runner.system.commit_log", CommitLog(workspace_id=workspace.id, max=limit))
    return list(data.get("commits", [])) if data else []


def _retrospective(request: TurnRequest, project_id: Any, *_: Any) -> list[str]:
    return ["Write retrospective.md from this project summary:", project_summary(project_id)]


def project_summary(project_id: Any) -> str:
    """Iterations per task, gate decisions, turns and cost per phase (retrospective input)."""
    lines = ["Tasks (id: iterations, status):"]
    for task in Task.objects.filter(project_id=project_id, parent__isnull=True).order_by("order"):
        iterations = max(
            [task.iteration, *task.children.values_list("iteration", flat=True)], default=1
        )
        lines.append(f"- {task.external_id} {task.title}: {iterations}, {task.status}")
    lines.append("Gates (id: decision, comment):")
    for gate in Gate.objects.filter(project_id=project_id).order_by("opened_at"):
        comment = f", {gate.comment[:200]}" if gate.comment else ""
        lines.append(f"- {gate.gate_id} ({gate.type}): {gate.decision or gate.status}{comment}")
    lines.append("Turns and cost per phase:")
    per_phase = (
        AgentTurn.objects.filter(project_id=project_id)
        .values("phase_run__phase_id")
        .annotate(turns=Count("id"), cost=Sum("cost"))
        .order_by("phase_run__phase_id")
    )
    for row in per_phase:
        lines.append(f"- {row['phase_run__phase_id']}: {row['turns']} turns, {row['cost']} EUR")
    return "\n".join(lines)


STEP: dict[str, Any] = {
    "analyst": _analyst,
    "architect": _architect,
    "planning:project_manager": _planning,
    "recruiter": _recruiter,
    "replan": _replan,
    "developer": _developer,
    "reviewer": _reviewer,
    "tester": _tester,
    "integration_test": _integration,
    "smoke": _smoke,
    "release:project_manager": _release,
    "retrospective:project_manager": _retrospective,
}

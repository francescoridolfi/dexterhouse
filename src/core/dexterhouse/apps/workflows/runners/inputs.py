# SPDX-License-Identifier: AGPL-3.0-or-later
"""`TurnRequest` -> `TurnInputs`: what a turn reads, per agents/handoffs.md.

Processes do not declare the input artifacts of a step yet, so the defaults below follow
the hand-off table: each step reads the latest version of the kinds listed for it (first
match of `<phase>:<step>`, `<step>`, `<role>`). Inside a loop, `dev_notes`, `review` and
`test_report` are limited to the current task. E-04 refines this with the real prompts.
"""

from typing import Any

from django.db.models import Max

from dexterhouse.apps.agents.models import AgentInstance, AgentStatus
from dexterhouse.apps.agents.schemas import ArtifactInput, NoteInput, TaskInput, TurnInputs
from dexterhouse.apps.projects.models import Artifact, Note
from dexterhouse.apps.workflows.models import StepRun, Task
from dexterhouse.apps.workflows.roles import installed_roles
from dexterhouse.apps.workflows.runner import TurnRequest

DEFAULT_INPUTS: dict[str, tuple[str, ...]] = {
    "analyst": ("brief", "questions", "requirements", "user_stories"),
    "architect": ("requirements", "user_stories"),
    "project_manager": ("architecture", "stack", "requirements", "user_stories"),
    "recruiter": ("task_board", "stack", "architecture"),
    "replan": ("task_board", "team_proposal"),
    "developer": ("task_board", "stack", "architecture"),
    "reviewer": ("stack", "architecture", "dev_notes"),
    "tester": ("stack", "dev_notes", "review"),
    "integration_test": ("task_board", "stack"),
    "smoke": ("stack",),
    "release:project_manager": ("test_report", "task_board", "assumptions"),
    "retrospective:project_manager": ("release_notes", "test_report", "assumptions"),
}
TASK_KINDS = frozenset({"dev_notes", "review", "test_report"})


def input_kinds(request: TurnRequest) -> tuple[str, ...]:
    keys = (f"{request.phase_id}:{request.step}", request.step, request.role)
    return next((DEFAULT_INPUTS[k] for k in keys if k in DEFAULT_INPUTS), ())


def _latest(project_id: Any, kinds: tuple[str, ...], task_ref: str | None) -> list[Artifact]:
    """Latest version of every (kind, name) of `kinds`, in the order of `kinds`."""
    rows = Artifact.objects.filter(project_id=project_id, kind__in=kinds)
    latest = rows.values("kind", "name").annotate(v=Max("version"))
    wanted = {(r["kind"], r["name"], r["v"]) for r in latest}
    artifacts = [a for a in rows.order_by("created_at") if (a.kind, a.name, a.version) in wanted]
    if task_ref:
        artifacts = [a for a in artifacts if a.kind not in TASK_KINDS or task_ref in a.name]
    return sorted(artifacts, key=lambda a: kinds.index(a.kind))


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


def _roles(project_id: Any) -> list[str]:
    hired = AgentInstance.objects.filter(project_id=project_id).exclude(status=AgentStatus.RELEASED)
    return sorted(installed_roles() | set(hired.values_list("role", flat=True)))


def _task_ids(project_id: Any) -> list[str] | None:
    """Task ids of the latest board and of the tasks created from it (proposal checks)."""
    ids = set(
        Task.objects.filter(project_id=project_id, parent__isnull=True).values_list(
            "external_id", flat=True
        )
    )
    board = Artifact.objects.filter(project_id=project_id, kind="task_board")
    latest = board.order_by("-created_at").first()
    if latest is not None and latest.data:
        ids |= {t["external_id"] for t in latest.data.get("tasks", [])}
    return sorted(ids) or None


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
        step_description=_describe(request),
        task=TaskInput(
            external_id=task.external_id,
            title=task.title,
            description=task.description,
            acceptance=task.acceptance,
            iteration=task.iteration,
            max_iterations=task.max_iterations,
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
    )


def _describe(request: TurnRequest) -> str:
    lines = [
        f"Process {request.process}, phase `{request.phase_id}`, step `{request.step}` "
        f"(role {request.role}, round {request.round}, {request.execution_mode} mode)."
    ]
    if request.produces:
        lines.append(f"Produce these artifacts: {', '.join(request.produces)}.")
    if request.verdict_rule != "none":
        lines.append(f"Give a `{request.verdict_rule}` verdict.")
    if request.may_ask:
        lines.append("You may ask the human questions with `project.ask` in supervised mode.")
    if request.task and request.task.branch:
        lines.append(f"Work on branch `{request.task.branch}`.")
    return "\n".join(lines)

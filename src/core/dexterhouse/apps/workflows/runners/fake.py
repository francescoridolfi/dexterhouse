# SPDX-License-Identifier: AGPL-3.0-or-later
"""`FakeTurnRunner`: deterministic canned outputs, valid per role, for tests and demos.

Behaviour is scripted with `settings.WORKFLOWS_FAKE_RUNNER` (all keys optional):

- `delay_s`: seconds each turn takes (crash-recovery tests);
- `ask_questions` (default True): a `may_ask` step asks once in supervised mode;
- `tasks` (default 3): tasks on the board, `T-02` and `T-03` depend on `T-01`;
- `hire` (default False): the recruiter proposes one package, so `replan` runs;
- `verdicts`: `{"reviewer:T-02": ["request_changes", "approve"], "tester:smoke": ["fail"]}`,
  indexed by task iteration (or attempt outside loops); missing entries are positive;
- `fail`: `{"architect": 2}` raises `TurnFailedError` on the first N attempts of a role;
- `fail_code` (default `provider_error`): the code of those failures.
"""

import time
from typing import Any

from django.conf import settings

from dexterhouse.apps.workflows.runner import TurnFailedError, TurnRequest
from dexterhouse_schema import TurnOutput, validate_turn_output

DEFAULT_TASKS = 3
TEXT_NAMES = {
    "requirements": "requirements.md",
    "user_stories": "user_stories.md",
    "architecture": "architecture.md",
    "adr": "adr/0001-stack.md",
    "release_notes": "release_notes.md",
    "retrospective": "retrospective.md",
    "brief": "brief.md",
    "file": "README.md",
}
ROLE_DEFAULT_KINDS = {"developer": "dev_notes", "reviewer": "review", "tester": "test_report"}


class FakeTurnRunner:
    """Implements `TurnRunner` without any LLM."""

    def __init__(self, script: dict[str, Any] | None = None) -> None:
        self.script = dict(settings.WORKFLOWS_FAKE_RUNNER if script is None else script)

    def run(self, request: TurnRequest) -> TurnOutput:
        if delay := float(self.script.get("delay_s", 0)):
            time.sleep(delay)
        if request.attempt <= int(self.script.get("fail", {}).get(request.role, 0)):
            code = self.script.get("fail_code", "provider_error")
            raise TurnFailedError(code, f"scripted failure of {request.role}")
        data = self._output(request)
        return validate_turn_output(data, request.turn_context())

    def _output(self, request: TurnRequest) -> dict[str, Any]:
        if self._asks(request):
            return {
                "status": "waiting_answers",
                "summary": "Two questions before writing the requirements.",
                "artifacts": [self.questions()],
            }
        kinds = list(request.produces) or [ROLE_DEFAULT_KINDS.get(request.role, "dev_notes")]
        if request.role.endswith("developer") and not request.produces:
            kinds = ["dev_notes"]
        verdict = self._verdict(request) if request.verdict_rule != "none" else None
        artifacts = [self._artifact(kind, request, verdict) for kind in kinds]
        assumptions: list[str] = []
        if request.may_ask and request.execution_mode == "autonomous":
            artifacts.append(self.assumptions())
            assumptions = ["No payments in 1.0"]
        if request.verdict_rule == "review" and "review" not in kinds:
            artifacts.append(self._artifact("review", request, verdict))
        if request.verdict_rule == "test" and "test_report" not in kinds:
            artifacts.append(self._artifact("test_report", request, verdict))
        return {
            "status": "done",
            "summary": f"{request.role} completed {request.step} (round {request.round}).",
            "artifacts": artifacts,
            "verdict": verdict,
            "assumptions_made": assumptions,
        }

    def _asks(self, request: TurnRequest) -> bool:
        return (
            request.may_ask
            and request.execution_mode == "supervised"
            and not request.answers
            and request.round == 0
            and bool(self.script.get("ask_questions", True))
        )

    def _verdict(self, request: TurnRequest) -> str:
        key = request.task.external_id if request.task else request.step
        index = (request.task.iteration if request.task else request.attempt) - 1
        planned = self.script.get("verdicts", {}).get(f"{request.role}:{key}", [])
        positive = "approve" if request.verdict_rule == "review" else "pass"
        return planned[index] if index < len(planned) else positive

    def _artifact(self, kind: str, request: TurnRequest, verdict: str | None) -> dict[str, Any]:
        if kind in TEXT_NAMES:
            return {
                "kind": kind,
                "name": TEXT_NAMES[kind],
                "content": f"# {kind.replace('_', ' ').title()}\n\n{self._context_line(request)}\n",
            }
        builders = {
            "dev_notes": self.dev_notes,
            "stack": lambda _r, _v: {"kind": "stack", "name": "stack.yaml", "data": self.stack()},
            "task_board": lambda _r, _v: self.task_board(),
            "team_proposal": lambda _r, _v: self.team_proposal(),
            "questions": lambda _r, _v: self.questions(),
            "assumptions": lambda _r, _v: self.assumptions(),
            "review": self.review,
            "test_report": self.test_report,
        }
        return builders[kind](request, verdict)

    @staticmethod
    def _context_line(request: TurnRequest) -> str:
        parts = [f"Produced by the fake {request.role} for phase {request.phase_id}."]
        if request.comment:
            parts.append(f"Addresses: {request.comment}")
        if request.answers:
            parts.append("Answers: " + "; ".join(a.answer for a in request.answers))
        return " ".join(parts)

    def dev_notes(self, request: TurnRequest, _verdict: str | None) -> dict[str, Any]:
        task = request.task
        name = f"dev_notes/{task.external_id}-iter{task.iteration}.md" if task else "dev_notes.md"
        return {"kind": "dev_notes", "name": name, "content": "# Dev notes\n\nDone.\n"}

    @staticmethod
    def stack() -> dict[str, Any]:
        return {
            "language": "python",
            "framework": "django",
            "workspace_image": "dexterhouse/workspace:python",
            "package_manager": "uv",
            "test_command": "uv run pytest -q",
            "run_command": "uv run manage.py runserver 0.0.0.0:8000",
            "services": ["postgres"],
            "ports": [8000],
        }

    def task_board(self) -> dict[str, Any]:
        count = int(self.script.get("tasks", DEFAULT_TASKS))
        tasks = [
            {
                "external_id": f"T-{n:02d}",
                "title": f"Task {n}",
                "description": f"Implement part {n} of the brief.",
                "acceptance": [f"Part {n} works and is tested"],
                "depends_on": [] if n == 1 else ["T-01"],
                "estimate": "S",
                "assigned_role": "developer",
            }
            for n in range(1, count + 1)
        ]
        return {"kind": "task_board", "name": "task_board.json", "data": {"tasks": tasks}}

    def team_proposal(self) -> dict[str, Any]:
        proposals = []
        if self.script.get("hire"):
            proposals.append(
                {
                    "name": "htmx-frontend-developer",
                    "version": "1.3.0",
                    "role": "htmx_frontend_developer",
                    "reason": "Better templates than the generic developer.",
                    "for_tasks": ["T-01"],
                    "risk": "low",
                    "verified": True,
                    "rating": 4.6,
                    "installs": 812,
                    "author_github": "dexterhouse-community",
                }
            )
        data = {"marketplace_status": "reachable", "proposals": proposals, "summary": "Team ok."}
        return {"kind": "team_proposal", "name": "team_proposal.json", "data": data}

    @staticmethod
    def questions() -> dict[str, Any]:
        questions = [
            {
                "id": "q1",
                "text": "Will the app handle payments?",
                "kind": "boolean",
                "why": "Changes data model and compliance scope",
                "default_assumption": "No payments in 1.0",
            },
            {
                "id": "q2",
                "text": "Which language should the UI use?",
                "kind": "choice",
                "options": ["English", "Italian"],
                "why": "Copy and i18n",
                "default_assumption": "English",
            },
        ]
        return {"kind": "questions", "name": "questions.json", "data": {"questions": questions}}

    @staticmethod
    def assumptions() -> dict[str, Any]:
        item = {
            "id": "a1",
            "question": "Payments?",
            "assumed": "No payments in 1.0",
            "rationale": "The brief does not mention prices",
            "risk": "low",
        }
        return {"kind": "assumptions", "name": "assumptions.json", "data": {"assumptions": [item]}}

    def review(self, request: TurnRequest, verdict: str | None) -> dict[str, Any]:
        task = request.task
        iteration = task.iteration if task else 1
        findings = []
        if verdict == "request_changes":
            findings.append(
                {
                    "id": f"R-{iteration}",
                    "severity": "major" if iteration < 3 else "blocker",
                    "file": "app/services.py",
                    "title": "Capacity check not atomic",
                    "request": "Use select_for_update around the capacity check.",
                    "how_to_verify": "The concurrency test passes.",
                    "resolved": False,
                    "first_seen_iteration": iteration,
                }
            )
        data = {
            "task_id": task.external_id if task else "T-01",
            "iteration": iteration,
            "verdict": verdict or "approve",
            "summary": "Looks good." if not findings else "One blocking finding.",
            "findings": findings,
            "blocking_count": len(findings),
        }
        name = f"reviews/{data['task_id']}-iter{iteration}.md"
        return {"kind": "review", "name": name, "data": data}

    def test_report(self, request: TurnRequest, verdict: str | None) -> dict[str, Any]:
        task = request.task
        scope = "task" if task else {"smoke": "smoke"}.get(request.step, "integration")
        failed = 1 if verdict == "fail" else 0
        data: dict[str, Any] = {
            "scope": scope,
            "command": "uv run pytest -q",
            "exit_code": failed,
            "passed": 5,
            "failed": failed,
            "skipped": 0,
            "duration_s": 1.5,
            "verdict": verdict or "pass",
            "failures": [{"test": "tests/test_app.py::test_flow", "message": "boom"}]
            if failed
            else [],
        }
        if task:
            data.update(task_id=task.external_id, iteration=task.iteration)
        if scope == "smoke":
            data["smoke"] = {"url": "http://localhost:8000/", "status": 200, "startup_s": 1.0}
        suffix = f"{task.external_id}-iter{task.iteration}" if task else request.step
        return {"kind": "test_report", "name": f"test_reports/{suffix}.json", "data": data}

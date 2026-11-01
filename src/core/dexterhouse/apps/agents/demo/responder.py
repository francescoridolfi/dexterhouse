# SPDX-License-Identifier: AGPL-3.0-or-later
"""`respond`: the `fake` provider's answer for a built-in agent, by role and step.

The turn is found from the request metadata; its `TurnInputs` (what the workflow engine
gave the agent) decide the output. The first LLM call of a turn uses the agent's tools the
way its prompt asks (the analyst calls `project.ask` when the step allows questions, every
role loads its main skill and reads memory or the board), so the built-in MCP servers run
for real; the next call returns the TurnOutput JSON, valid for the step.

`settings.AGENTS_DEMO_SCRIPT` (all keys optional):

- `ask_questions` (default True): the analyst asks when the step allows it;
- `tasks` (default 3): tasks on the board, `T-01` is the scaffold;
- `hire` (default False): the recruiter proposes `htmx-frontend-developer`;
- `verdicts`: `{"reviewer:T-02": ["request_changes", "approve"], "tester:smoke": ["fail"]}`,
  indexed by task iteration (or step attempt outside loops); missing entries are positive.
"""

import json
import re
from dataclasses import dataclass, field
from typing import Any

from django.conf import settings

from dexterhouse.apps.agents.demo import content
from dexterhouse.apps.agents.models import AgentTurn
from dexterhouse.apps.agents.schemas import TurnInputs
from dexterhouse.apps.gateway.messages import CompletionRequest, ToolCallPart, ToolResultPart
from dexterhouse.apps.gateway.providers.fake import FakeResponse, FakeToolCall

DEFAULT_TASKS = 3
SKILLS = {
    "analyst": "requirements-elicitation",
    "architect": "architecture-decision",
    "planning": "task-decomposition",
    "replan": "task-decomposition",
    "release": "release-notes",
    "retrospective": "retrospective-format",
    "recruiter": "team-sizing",
    "developer": "secure-coding-basics",
    "reviewer": "review-checklist",
    "tester": "acceptance-to-tests",
}
_ANSWER = re.compile(r"^(q\d+): (.*)$")


@dataclass
class Turn:
    """What the responder knows about the turn it answers."""

    role: str
    step: str
    phase: str
    attempt: int
    inputs: TurnInputs
    tools: set[str]
    script: dict[str, Any]
    calls: dict[str, str] = field(default_factory=dict)  # tool name -> result text

    @property
    def kind(self) -> str:
        """The role, with hired developers treated as developers."""
        return "developer" if self.role.endswith("developer") else self.role

    @property
    def task_ref(self) -> str | None:
        return self.inputs.task.external_id if self.inputs.task else None

    @property
    def iteration(self) -> int:
        task = self.inputs.task
        return task.iteration if task and task.iteration else 1

    def verdict(self, positive: str) -> str:
        key = self.task_ref or self.step
        index = (self.iteration if self.task_ref else self.attempt) - 1
        planned = self.script.get("verdicts", {}).get(f"{self.role}:{key}", [])
        return planned[index] if index < len(planned) else positive


def respond(request: CompletionRequest) -> FakeResponse:
    agent_turn = AgentTurn.objects.select_related("agent_instance", "phase_run").get(
        pk=request.metadata["agent_turn_id"]
    )
    turn = Turn(
        role=agent_turn.agent_instance.role,
        step=agent_turn.step,
        phase=agent_turn.phase_run.phase_id if agent_turn.phase_run else "",
        attempt=agent_turn.step_attempt,
        inputs=TurnInputs.model_validate(agent_turn.inputs),
        tools={t.name for t in request.tools},
        script=dict(getattr(settings, "AGENTS_DEMO_SCRIPT", {})),
        calls=_tool_results(request),
    )
    if not any(m.role == "assistant" for m in request.messages):
        calls = first_calls(turn)
        if calls:
            return FakeResponse(text="Let me check first.", tool_calls=calls)
    output = final_output(turn)
    return FakeResponse(text="Done.\n" + json.dumps(output, ensure_ascii=False))


def _tool_results(request: CompletionRequest) -> dict[str, str]:
    names = {p.id: p.name for m in request.messages for p in m.parts if isinstance(p, ToolCallPart)}
    return {
        names.get(p.call_id, ""): p.content
        for m in request.messages
        for p in m.parts
        if isinstance(p, ToolResultPart)
    }


# First call: tools ------------------------------------------------------------------------


def wants_to_ask(turn: Turn) -> bool:
    inputs = turn.inputs
    reopened = any(a.startswith("Gate comment:") for a in inputs.gate_answers)
    return (
        turn.kind == "analyst"
        and inputs.may_ask
        and not inputs.gate_answers
        and not reopened
        and bool(turn.script.get("ask_questions", True))
    )


def first_calls(turn: Turn) -> list[FakeToolCall]:
    calls: list[FakeToolCall] = []
    if wants_to_ask(turn) and "project.ask" in turn.tools:
        return [FakeToolCall(id="ask", name="project.ask", args={"questions": content.QUESTIONS})]
    skill = SKILLS.get(turn.phase if turn.kind == "project_manager" else turn.kind)
    if turn.step == "replan":
        skill = SKILLS["replan"]
    if skill and "skills.read" in turn.tools:
        calls.append(FakeToolCall(id="skill", name="skills.read", args={"name": skill}))
    if "memory.search" in turn.tools:
        query = turn.inputs.task.title if turn.inputs.task else turn.step
        calls.append(FakeToolCall(id="memory", name="memory.search", args={"query": query}))
    elif "project.tasks" in turn.tools:
        calls.append(FakeToolCall(id="tasks", name="project.tasks", args={}))
    return calls


# Final call: the TurnOutput ---------------------------------------------------------------


def final_output(turn: Turn) -> dict[str, Any]:
    builders = {
        "analyst": _analyst,
        "architect": _architect,
        "project_manager": _project_manager,
        "recruiter": _recruiter,
        "developer": _developer,
        "reviewer": _reviewer,
        "tester": _tester,
    }
    builder = builders.get(turn.kind)
    if builder is None:
        return {
            "status": "blocked",
            "summary": f"The demo responder has no script for role {turn.role}.",
            "artifacts": [],
            "blocked_reason": "out_of_scope",
        }
    return builder(turn)


def _done(summary: str, artifacts: list[dict[str, Any]], **extra: Any) -> dict[str, Any]:
    return {"status": "done", "summary": summary[:400], "artifacts": artifacts, **extra}


def _answers(inputs: TurnInputs) -> dict[str, str]:
    return {m[1]: m[2] for line in inputs.gate_answers if (m := _ANSWER.match(line))}


def _analyst(turn: Turn) -> dict[str, Any]:
    inputs = turn.inputs
    brief = content.artifact(inputs, "brief")
    previous = content.artifact(inputs, "requirements")
    reqs = (
        content.parse_requirements(inputs)
        if previous
        else content.requirements_from_brief(brief.content or "" if brief else "")
    )
    answers = _answers(inputs)
    comment = next((a for a in inputs.gate_answers if a.startswith("Gate comment:")), None)
    asked = '"mode": "ask"' in turn.calls.get("project.ask", "")
    changelog = []
    if answers:
        changelog.append("v2: " + "; ".join(f"{k} answered: {v}" for k, v in answers.items()))
    if comment:
        changelog.append(f"Addressed {comment}")
    open_points = [f"{k}: {v}" for k, v in answers.items()]
    if asked:
        open_points = [f"{q['id']}: {q['text']} (asked)" for q in content.QUESTIONS]
    elif not answers:
        open_points = [f"a{n}: assumed, see assumptions.json" for n in (1, 2, 3)]
    docs = [
        {
            "kind": "requirements",
            "name": "requirements.md",
            "content": content.requirements_md(
                reqs, draft=asked, changelog=changelog, open_points=open_points
            ),
        },
        {
            "kind": "user_stories",
            "name": "user_stories.md",
            "content": content.user_stories_md(reqs, draft=asked),
        },
    ]
    if asked:
        questions = {"kind": "questions", "name": "questions.json"}
        questions["data"] = {"questions": content.QUESTIONS}
        return {
            "status": "waiting_answers",
            "summary": f"{len(content.QUESTIONS)} questions before the final requirements.",
            "artifacts": [questions, *docs],
        }
    if answers:
        return _done(f"Requirements v2 with {len(reqs)} functional requirements.", docs)
    data = content.assumptions_data()
    assumed = [a["assumed"] for a in data["assumptions"]]
    return _done(
        f"{len(reqs)} functional requirements; {len(assumed)} assumptions recorded.",
        [*docs, {"kind": "assumptions", "name": "assumptions.json", "data": data}],
        assumptions_made=assumed,
    )


def _architect(turn: Turn) -> dict[str, Any]:
    reqs = content.parse_requirements(turn.inputs)
    comment = next(
        (
            a.removeprefix("Gate comment: ")
            for a in turn.inputs.gate_answers
            if a.startswith("Gate comment:")
        ),
        None,
    )
    return _done(
        "Architecture, two ADRs and stack.yaml.",
        [
            {
                "kind": "architecture",
                "name": "architecture.md",
                "content": content.architecture_md(reqs, comment),
            },
            *content.adrs(reqs),
            {"kind": "stack", "name": "stack.yaml", "data": content.STACK},
        ],
    )


def _project_manager(turn: Turn) -> dict[str, Any]:
    inputs = turn.inputs
    if turn.step == "replan":
        board = content.artifact(inputs, "task_board")
        proposal = content.artifact(inputs, "team_proposal")
        data = content.replanned(
            board.data if board else {"tasks": []},
            (proposal.data or {}).get("proposals", []) if proposal else [],
            set(inputs.installed_roles or []),
        )
        return _done(
            "Task board re-planned for the new team.",
            [{"kind": "task_board", "name": "task_board.json", "data": data}],
        )
    if turn.phase == "release":
        return _done(
            "Release notes from the merged tasks and test reports.",
            [
                {
                    "kind": "release_notes",
                    "name": "release_notes.md",
                    "content": content.release_notes_md(inputs),
                }
            ],
        )
    if turn.phase == "retrospective":
        return _done(
            "Retrospective from the project summary.",
            [
                {
                    "kind": "retrospective",
                    "name": "retrospective.md",
                    "content": content.retrospective_md(inputs.step_description),
                }
            ],
        )
    reqs = content.parse_requirements(inputs)
    board = content.task_board(
        reqs,
        content.parse_stories(inputs),
        int(turn.script.get("tasks", DEFAULT_TASKS)),
    )
    return _done(
        f"Task board with {len(board['tasks'])} tasks.",
        [{"kind": "task_board", "name": "task_board.json", "data": board}],
    )


def _recruiter(turn: Turn) -> dict[str, Any]:
    data = content.team_proposal(
        bool(turn.script.get("hire")),
        turn.inputs.task_ids or [],
        reachable="marketplace.search" in turn.tools,
    )
    return _done(
        data["summary"], [{"kind": "team_proposal", "name": "team_proposal.json", "data": data}]
    )


def _developer(turn: Turn) -> dict[str, Any]:
    ref = turn.task_ref or "T-00"
    name = f"dev_notes/{ref}-iter{turn.iteration}.md"
    notes = content.dev_notes_md(ref, turn.iteration, turn.inputs.review_items)
    return _done(
        f"{ref} iteration {turn.iteration} implemented (demo).",
        [{"kind": "dev_notes", "name": name, "content": notes}],
        handoff={"to_step": "reviewer", "notes": "Ready for review."},
    )


def _reviewer(turn: Turn) -> dict[str, Any]:
    reviews = content.artifacts(turn.inputs, "review")
    if turn.task_ref:
        ref, iteration = turn.task_ref, turn.iteration
        mine = [r for r in reviews if ref in r.name]
        name = f"reviews/{ref}-iter{iteration}.md"
    else:  # repository review (code-review-only)
        ref, mine = "T-00", [r for r in reviews if "repository" in r.name]
        iteration = len(mine) + 1
        name = f"reviews/repository-iter{iteration}.md"
    latest = max(mine, key=lambda r: (r.data or {}).get("iteration", 0), default=None)
    previous = (latest.data or {}).get("findings", []) if latest else []
    known = turn.inputs.known_finding_ids
    if known is None:
        known = sorted({f["id"] for r in mine for f in (r.data or {}).get("findings", [])})
    data = content.review_data(ref, iteration, turn.verdict("approve"), previous, known)
    verdict = data["verdict"]
    return _done(
        f"Review of {ref} iteration {iteration}: {verdict}.",
        [{"kind": "review", "name": name, "data": data}],
        verdict=verdict,
        handoff={"to_step": "tester" if verdict == "approve" else "developer"},
    )


def _tester(turn: Turn) -> dict[str, Any]:
    inputs = turn.inputs
    command = inputs.stack_test_command or "uv run pytest -q"
    verdict = turn.verdict("pass")
    if turn.task_ref:
        acceptance = len(inputs.task.acceptance) if inputs.task else 1
        data = content.build_test_report(
            "task",
            verdict,
            f"{command} tests/acceptance",
            task_ref=turn.task_ref,
            iteration=turn.iteration,
            acceptance=acceptance,
        )
        name = f"test_reports/{turn.task_ref}-iter{turn.iteration}.json"
    else:
        scope = "smoke" if turn.step == "smoke" else "integration"
        data = content.build_test_report(scope, verdict, command)
        name = f"test_reports/{turn.step}.json"
    extra: dict[str, Any] = {"verdict": data["verdict"]}
    if data["verdict"] == "fail":
        extra["handoff"] = {"to_step": "developer"}
    return _done(
        f"{data['passed']} passed, {data['failed']} failed (demo).",
        [{"kind": "test_report", "name": name, "data": data}],
        **extra,
    )

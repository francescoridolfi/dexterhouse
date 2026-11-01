# SPDX-License-Identifier: AGPL-3.0-or-later
"""Artifacts of the demo responder, built from the brief and the upstream artifacts.

Everything follows the templates and schemas of agents/artifact_templates.md and
artifact_schemas_*.md, so the structural checks of the brief samples suite hold; the text
itself is generic and says it comes from the demo responder.
"""

import re
from dataclasses import dataclass
from typing import Any

from dexterhouse.apps.agents.schemas import ArtifactInput, TurnInputs

DEMO = "Produced by the DexterHouse demo responder (no LLM, nothing was executed)."
MIN_FEATURES = 3
MAX_FEATURES = 8
_REQUIREMENT = re.compile(r"^- (F-\d+) (.+?) \(priority: (must|should|could)\)", re.MULTILINE)
_STORY = re.compile(r"^## (US-\d+) (.+?) \(covers ([^)]+)\)", re.MULTILINE)
_FILLER = re.compile(r"^(a|an|the|we need|we want|i want|build|create|make)\s+", re.IGNORECASE)
STACK = {
    "language": "python",
    "framework": "django",
    "workspace_image": "dexterhouse/workspace:python",
    "package_manager": "uv",
    "test_command": "uv run pytest -q",
    "run_command": "uv run manage.py runserver 0.0.0.0:8000",
    "lint_command": "uv run ruff check .",
    "install_command": "uv sync",
    "services": [],
    "env": {"DJANGO_SETTINGS_MODULE": "app.settings"},
    "ports": [8000],
    "healthcheck_path": "/health",
    "notes": "SQLite in development; " + DEMO,
}
QUESTIONS = [
    {
        "id": "q1",
        "text": "Will the application handle payments?",
        "kind": "boolean",
        "why": "Changes the data model and the compliance scope.",
        "default_assumption": "No payments in the first release",
    },
    {
        "id": "q2",
        "text": "Which language should the user interface use?",
        "kind": "choice",
        "options": ["English", "Italian", "Both"],
        "why": "Changes copy, formats and the i18n effort.",
        "default_assumption": "English",
    },
    {
        "id": "q3",
        "text": "Which user roles are needed?",
        "kind": "choice",
        "options": ["Customers only", "Customers and staff", "Customers, staff and admin"],
        "why": "Changes authorization rules and the number of screens.",
        "default_assumption": "Customers and staff",
    },
]


@dataclass(frozen=True)
class Requirement:
    id: str
    text: str
    priority: str


def artifact(inputs: TurnInputs, kind: str) -> ArtifactInput | None:
    """The first input artifact of `kind` (inputs are in priority order)."""
    return next((a for a in inputs.artifacts if a.kind == kind), None)


def artifacts(inputs: TurnInputs, kind: str) -> list[ArtifactInput]:
    return [a for a in inputs.artifacts if a.kind == kind]


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "item"


# Analysis -------------------------------------------------------------------------------


def features(brief: str) -> list[str]:
    """Short capability phrases from the brief, between 3 and 8 (padded if it is terse)."""
    parts = re.split(r"[.;:\n!?]|,\s*|\s+and\s+|\s+with\s+", re.sub(r"\s+", " ", brief))
    found: list[str] = []
    for part in parts:
        phrase = _FILLER.sub("", part.strip()).strip(" -")
        if len(phrase) >= 4 and phrase.lower() not in {p.lower() for p in found}:
            found.append(phrase[:80])
    padding = ["user accounts and sign-in", "administration of the main records", "search"]
    for extra in padding:
        if len(found) >= MIN_FEATURES:
            break
        found.append(extra)
    return found[:MAX_FEATURES]


def requirements_from_brief(brief: str) -> list[Requirement]:
    return [
        Requirement(f"F-{n:02d}", f"Users can work with {phrase}.", "must" if n <= 3 else "should")
        for n, phrase in enumerate(features(brief), start=1)
    ]


def requirements_md(
    reqs: list[Requirement],
    *,
    draft: bool,
    changelog: list[str],
    open_points: list[str],
    project: str = "the project",
) -> str:
    head = "> DRAFT pending answers\n\n" if draft else ""
    functional = "\n".join(
        f"- {r.id} {r.text} (priority: {r.priority}) — covered by: US-{r.id[2:]}" for r in reqs
    )
    return f"""{head}# Requirements — {project}

## Changelog
{_bullets(changelog or ["v1: first version from the brief."])}

## Context
The client asked for the system described in the brief. {DEMO}

## Actors
| actor | goals |
|---|---|
| Customer | use the main features of the application |
| Staff | manage the records customers rely on |

## Functional requirements
{functional}

## Non-functional requirements
- N-01 95% of requests answer in under 500 ms with 20 concurrent users.
- N-02 Every endpoint checks the caller's role.
- N-03 The application starts with one documented command.

## Constraints declared by the client
- The application must run with Docker.

## Out of scope
- Native mobile applications: not requested in the brief.

## Open points
{_bullets(open_points or ["None."])}
"""


def user_stories_md(reqs: list[Requirement], *, draft: bool) -> str:
    head = "> DRAFT pending answers\n\n" if draft else ""
    stories = []
    for req in reqs:
        number = req.id[2:]
        stories.append(
            f"""## US-{number} {req.text.rstrip(".")} (covers {req.id})
As a customer, I want {req.text[0].lower()}{req.text[1:-1]}, so that I reach my goal.
Acceptance:
- Given a signed-in customer, when they use it with valid data, then the change is shown.
- Given invalid data, when they submit it, then they see an error and nothing is saved."""
        )
    return head + "# User stories\n\n" + "\n\n".join(stories) + "\n"


def assumptions_data(answers: dict[str, str] | None = None) -> dict[str, Any]:
    return {
        "assumptions": [
            {
                "id": f"a{n}",
                "question": q["text"],
                "assumed": (answers or {}).get(q["id"], q["default_assumption"]),
                "rationale": "The brief does not say; this is the smallest safe choice.",
                "risk": "medium" if n == 1 else "low",
            }
            for n, q in enumerate(QUESTIONS, start=1)
        ]
    }


def parse_requirements(inputs: TurnInputs) -> list[Requirement]:
    req = artifact(inputs, "requirements")
    found = _REQUIREMENT.findall(req.content or "") if req else []
    if found:
        return [Requirement(i, t, p) for i, t, p in found]
    brief = artifact(inputs, "brief")
    return requirements_from_brief(brief.content or "" if brief else "")


def parse_stories(inputs: TurnInputs) -> dict[str, list[str]]:
    """Story ids by requirement id."""
    doc = artifact(inputs, "user_stories")
    covered: dict[str, list[str]] = {}
    for story, _title, covers in _STORY.findall(doc.content or "" if doc else ""):
        for req in re.findall(r"F-\d+", covers):
            covered.setdefault(req, []).append(story)
    return covered


# Architecture ---------------------------------------------------------------------------


def architecture_md(reqs: list[Requirement], comment: str | None) -> str:
    changes = f"## Changes in this version\n- Addressed: {comment}\n\n" if comment else ""
    modules = "\n".join(
        f"| {slug(r.text.removeprefix('Users can work with '))[:24]} | {r.text} | {r.id} |"
        for r in reqs
    )
    tree = "\n".join(
        f"  {slug(r.text.removeprefix('Users can work with '))[:24].replace('-', '_')}/"
        for r in reqs
    )
    return f"""# Architecture — demo
{changes}## Overview
A Django monolith with server-rendered pages and a small REST API. {DEMO}

## Stack rationale
Python and Django on the python workspace image; details in adr/0001-stack.md.

## Modules and responsibilities
| module | responsibility | requirements |
|---|---|---|
{modules}

## Data model
| entity | fields | notes |
|---|---|---|
| User | id, email, role | Django auth |
| Record | id, owner, title, created_at | one table per module in practice |

## API / interface contracts
| method path | purpose | auth |
|---|---|---|
| GET /health | liveness | none |
| GET/POST /api/<module>/ | list and create records | session |

## Repository layout
```
app/
{tree}
tests/
  acceptance/
manage.py
pyproject.toml
```

## How to run and test
`uv sync`, then `uv run manage.py runserver 0.0.0.0:8000`; tests with `uv run pytest -q`.

## Technical risks and mitigations
- Concurrent updates of shared records: row locks in the services (adr/0002).

## Deferred decisions
- Background jobs: not needed by the requirements yet.
"""


def adrs(reqs: list[Requirement]) -> list[dict[str, Any]]:
    ids = ", ".join(r.id for r in reqs[:3])
    stack = f"""# ADR-0001 — Django monolith on the python workspace image
- Status: accepted · Requirements: {ids}
## Context
The requirements describe a small web application with a few roles. {DEMO}
## Decision
One Django project with server-rendered pages and a REST API.
## Alternatives considered
- Separate SPA and API: more moving parts than the requirements justify.
## Consequences
+ One process to run and test. - The UI stays simple.
"""
    risky = f"""# ADR-0002 — Row locks for concurrent updates
- Status: accepted · Requirements: {reqs[-1].id}, N-01
## Context
Two users can change the same record at the same time.
## Decision
Services lock the row (`select_for_update`) inside one transaction.
## Alternatives considered
- Optimistic versioning: more user-visible conflicts.
## Consequences
+ No lost updates. - Short waits under contention.
"""
    return [
        {"kind": "adr", "name": "adr/0001-stack.md", "content": stack},
        {"kind": "adr", "name": "adr/0002-row-locks.md", "content": risky},
    ]


# Planning -------------------------------------------------------------------------------


def task_board(
    reqs: list[Requirement], stories: dict[str, list[str]], count: int
) -> dict[str, Any]:
    """T-01 scaffold, then `count - 1` slices that cover every requirement round-robin."""
    slices = max(count - 1, 1)
    groups: list[list[Requirement]] = [[] for _ in range(slices)]
    for index, req in enumerate(reqs):
        groups[index % slices].append(req)
    tasks = [
        {
            "external_id": "T-01",
            "title": "Repository scaffold",
            "description": "Create the layout of architecture.md with an empty test suite.",
            "acceptance": ["`uv run pytest -q` runs and exits 0 on the empty suite"],
            "depends_on": [],
            "estimate": "S",
            "assigned_role": "developer",
            "files_hint": ["pyproject.toml", "manage.py", "app/settings.py"],
            "covers": {"requirements": [], "stories": []},
        }
    ]
    for number, group in enumerate(groups, start=2):
        if not group:
            continue
        names = ", ".join(r.text.removeprefix("Users can work with ").rstrip(".") for r in group)
        tasks.append(
            {
                "external_id": f"T-{number:02d}",
                "title": f"Slice: {names}"[:120],
                "description": f"Model, API and pages for {names}.",
                "acceptance": [
                    f"{r.id}: {r.text} is verified by an acceptance test" for r in group
                ],
                "depends_on": ["T-01"],
                "estimate": "M",
                "assigned_role": "developer",
                "files_hint": [f"app/{slug(names)[:24].replace('-', '_')}/models.py"],
                "covers": {
                    "requirements": [r.id for r in group],
                    "stories": [s for r in group for s in stories.get(r.id, [])],
                },
            }
        )
    return {"tasks": tasks, "notes": DEMO}


def replanned(board: dict[str, Any], proposals: list[dict[str, Any]], roles: set[str]):
    tasks = [dict(t) for t in board.get("tasks", [])]
    for proposal in proposals:
        if proposal["role"] not in roles:
            continue
        for task in tasks:
            if task["external_id"] in proposal["for_tasks"]:
                task["assigned_role"] = proposal["role"]
    return {**board, "tasks": tasks}


def team_proposal(hire: bool, task_ids: list[str], reachable: bool) -> dict[str, Any]:
    proposals = []
    if hire and task_ids:
        proposals.append(
            {
                "name": "htmx-frontend-developer",
                "version": "1.3.0",
                "role": "htmx_frontend_developer",
                "reason": "Server-rendered UI tasks benefit from an htmx specialist.",
                "for_tasks": [task_ids[-1]],
                "permissions": [{"id": "project.tasks", "risk": "low"}],
                "risk": "low",
                "verified": True,
                "rating": 4.6,
                "installs": 812,
                "author_github": "dexterhouse-community",
            }
        )
    status = "reachable" if reachable or hire else "unreachable"
    summary = (
        "One specialist proposed for the UI task."
        if proposals
        else "No specialist needed: the built-in team covers the board."
    )
    if status == "unreachable":
        summary = "Marketplace tools unavailable: built-in team only."
    return {"marketplace_status": status, "proposals": proposals, "summary": summary}


# Delivery -------------------------------------------------------------------------------


def dev_notes_md(task_ref: str, iteration: int, items: list[dict[str, Any]]) -> str:
    responses = [
        f"- {item['id']}: done — {item.get('request', 'addressed')}"
        if "id" in item
        else f"- {item.get('test', 'test')}: done — fixed the failing behaviour"
        for item in items
    ]
    return f"""# Dev notes — {task_ref} (iteration {iteration})
## Done
- Implemented the task as described. {DEMO}
## How verified
- Not run: the demo responder executes nothing.
## Decisions
- None beyond the architecture.
## Responses
{_bullets(responses or ["No open findings or failures."])}
## Open points
- None.
"""


def review_data(
    task_ref: str,
    iteration: int,
    verdict: str,
    previous: list[dict[str, Any]],
    known: list[str],
) -> dict[str, Any]:
    """Carried findings keep id and first iteration; new ones continue the numbering."""
    numbers = [int(i[2:]) for i in known if i.startswith("R-") and i[2:].isdigit()]
    next_id = max(numbers, default=0) + 1
    findings = []
    for old in previous:
        resolved = verdict == "approve" or old["severity"] in {"minor", "nit"}
        findings.append({**old, "resolved": bool(old.get("resolved")) or resolved})
    blocking = [f for f in findings if f["severity"] in {"blocker", "major"} and not f["resolved"]]
    new: list[tuple[str, str]] = []
    if iteration == 1:
        new.append(("nit", "Name the helper after its behaviour"))
    if verdict == "request_changes" and not blocking:
        new.append(("major" if iteration < 3 else "blocker", "Acceptance criterion not covered"))
    for severity, title in new:
        findings.append(
            {
                "id": f"R-{next_id}",
                "severity": severity,
                "file": "app/services.py",
                "symbol": "handle",
                "title": title,
                "request": "Add the missing check and a test for it.",
                "how_to_verify": "The acceptance test of the criterion passes.",
                "resolved": False,
                "first_seen_iteration": iteration,
            }
        )
        next_id += 1
    count = sum(1 for f in findings if f["severity"] in {"blocker", "major"} and not f["resolved"])
    return {
        "task_id": task_ref,
        "iteration": iteration,
        "verdict": "request_changes" if count else "approve",
        "summary": f"{count} blocking finding(s). {DEMO}",
        "findings": findings,
        "blocking_count": count,
        "out_of_scope_notes": [],
    }


def build_test_report(
    scope: str,
    verdict: str,
    command: str,
    *,
    task_ref: str | None = None,
    iteration: int | None = None,
    acceptance: int = 1,
) -> dict[str, Any]:
    failed = 1 if verdict == "fail" else 0
    data: dict[str, Any] = {
        "scope": scope,
        "command": command,
        "exit_code": failed,
        "passed": acceptance + 2,
        "failed": failed,
        "skipped": 0,
        "duration_s": 1.5,
        "verdict": verdict,
        "failures": [{"test": "tests/acceptance/test_flow.py::test_main_flow", "message": "boom"}]
        if failed
        else [],
        "coverage_notes": f"Every acceptance criterion has a test. {DEMO}",
    }
    if task_ref:
        data.update(task_id=task_ref, iteration=iteration)
    if scope == "smoke":
        data["smoke"] = {"url": "http://localhost:8000/health", "status": 200, "startup_s": 1.0}
    return data


def release_notes_md(inputs: TurnInputs) -> str:
    board = artifact(inputs, "task_board")
    tasks = (board.data or {}).get("tasks", []) if board else []
    features_lines = [
        f"- {req} — {t['external_id']} {t['title']}"
        for t in tasks
        for req in t.get("covers", {}).get("requirements", [])
    ]
    assumed = artifact(inputs, "assumptions")
    assumption_lines = [
        f"- {a['id']}: {a['assumed']} (risk {a['risk']})"
        for a in ((assumed.data or {}).get("assumptions", []) if assumed else [])
    ]
    reports = artifacts(inputs, "test_report")
    known = [
        f"- {f['test']}: {f['message']}"
        for r in reports
        for f in (r.data or {}).get("failures", [])
    ]
    stack = artifact(inputs, "stack")
    run = (stack.data or {}).get("run_command", "see README") if stack else "see README"
    return f"""# Release notes — demo v1
## Summary
The planned tasks are merged and the suite is green. {DEMO}
## Features
{_bullets(features_lines or ["- See the task board."], prefixed=True)}
## Fixes
- None.
## Assumptions made
{_bullets(assumption_lines or ["- None."], prefixed=True)}
## Known issues
{_bullets(known or ["- None."], prefixed=True)}
## How to run
- `{run}`
## Commits
- Not available: no commit log was provided to this step.
"""


def retrospective_md(summary: str) -> str:
    tasks = [line for line in summary.splitlines() if line.startswith("- T-")]
    return f"""# Retrospective — demo
## Numbers
{_bullets(tasks or ["- No task data."], prefixed=True)}
## What worked
- Every phase produced its artifacts at the first attempt. {DEMO}
## What did not
- Nothing measurable in a demo run.
## Lessons → actions
| lesson | proposed action |
|---|---|
| Demo runs say nothing about quality | run the live job on a real provider |
## Cost vs estimate
- Demo turns cost nothing.
"""


def _bullets(lines: list[str], prefixed: bool = False) -> str:
    return "\n".join(line if prefixed or line.startswith("- ") else f"- {line}" for line in lines)

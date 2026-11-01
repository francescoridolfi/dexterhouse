# SPDX-License-Identifier: AGPL-3.0-or-later
"""Structural assertions on a project's artifacts (testing.md, row "Agenti").

They check schema, kind, names, mandatory sections, id threads and the numbering of review
findings, never the content: the same checks hold for the demo responder in CI and for a
real provider in the live job.
"""

import re
from collections import defaultdict
from typing import Any

from dexterhouse.apps.agents.models import AgentTurn
from dexterhouse.apps.projects.models import Artifact
from dexterhouse_schema.artifacts import validate_artifact

SECTIONS: dict[str, list[str]] = {
    "requirements": [
        "Changelog",
        "Context",
        "Actors",
        "Functional requirements",
        "Non-functional requirements",
        "Constraints declared by the client",
        "Out of scope",
        "Open points",
    ],
    "architecture": [
        "Overview",
        "Stack rationale",
        "Modules and responsibilities",
        "Data model",
        "API / interface contracts",
        "Repository layout",
        "How to run and test",
        "Technical risks and mitigations",
        "Deferred decisions",
    ],
    "adr": ["Context", "Decision", "Alternatives considered", "Consequences"],
    "dev_notes": ["Done", "How verified", "Decisions", "Responses", "Open points"],
    "release_notes": [
        "Summary",
        "Features",
        "Fixes",
        "Assumptions made",
        "Known issues",
        "How to run",
        "Commits",
    ],
    "retrospective": [
        "Numbers",
        "What worked",
        "What did not",
        "Lessons → actions",
        "Cost vs estimate",
    ],
}
NAMES: dict[str, str] = {
    "brief": r"^brief\.md$",
    "requirements": r"^requirements\.md$",
    "user_stories": r"^user_stories\.md$",
    "questions": r"^questions\.json$",
    "assumptions": r"^assumptions\.json$",
    "architecture": r"^architecture\.md$",
    "adr": r"^adr/\d{4}-[a-z0-9-]+\.md$",
    "stack": r"^stack\.yaml$",
    "task_board": r"^task_board\.json$",
    "team_proposal": r"^team_proposal\.json$",
    "dev_notes": r"^dev_notes/T-\d{2,3}-iter\d+\.md$",
    "review": r"^reviews/(T-\d{2,3}|repository)-iter\d+\.md$",
    "test_report": r"^test_reports/(T-\d{2,3}-iter\d+|integration_test|smoke)\.json$",
    "release_notes": r"^release_notes\.md$",
    "retrospective": r"^retrospective\.md$",
}
_HEADING = re.compile(r"^## (.+?)\s*$", re.MULTILINE)
_REQ = re.compile(r"^- (F-\d{2,3}) .+\(priority: (must|should|could)\)", re.MULTILINE)
_NFR = re.compile(r"^- (N-\d{2,3}) ", re.MULTILINE)
_STORY = re.compile(r"^## (US-\d{2,3}) .+\(covers ([^)]+)\)\s*$", re.MULTILINE)


def latest(project: Any) -> dict[tuple[str, str], Artifact]:
    """The latest version of every (kind, name)."""
    found: dict[tuple[str, str], Artifact] = {}
    for artifact in Artifact.objects.filter(project=project).order_by("version"):
        found[(artifact.kind, artifact.name)] = artifact
    return found


def of_kind(project: Any, kind: str) -> list[Artifact]:
    return [a for (k, _), a in sorted(latest(project).items()) if k == kind]


def headings(text: str) -> list[str]:
    return [h.split("  (")[0] for h in _HEADING.findall(text)]


def assert_sections(artifact: Artifact) -> None:
    expected = SECTIONS.get(artifact.kind)
    if expected is None:
        return
    found = [h for h in headings(artifact.content) if h in expected]
    assert found == expected, f"{artifact.name} v{artifact.version}: sections {found}"


def assert_artifacts_are_well_formed(project: Any) -> None:
    """Every version of every artifact: kind, name, schema or sections."""
    for artifact in Artifact.objects.filter(project=project):
        assert artifact.kind in NAMES, artifact.kind
        assert re.match(NAMES[artifact.kind], artifact.name), (artifact.kind, artifact.name)
        if artifact.data is not None:
            validate_artifact(artifact.kind, artifact.data)
        else:
            assert artifact.content.strip(), artifact.name
            assert_sections(artifact)


def requirement_ids(project: Any) -> dict[str, str]:
    """F-xx -> priority of the latest requirements."""
    (doc,) = of_kind(project, "requirements")
    ids = dict(_REQ.findall(doc.content))
    assert ids, "no functional requirement"
    assert _NFR.findall(doc.content), "no non-functional requirement"
    return ids


def assert_analysis(project: Any) -> None:
    """Ids are unique, every requirement has a story and every story a requirement."""
    reqs = requirement_ids(project)
    (stories,) = of_kind(project, "user_stories")
    covered: set[str] = set()
    story_ids = []
    for story, covers in _STORY.findall(stories.content):
        story_ids.append(story)
        refs = set(re.findall(r"F-\d{2,3}", covers))
        assert refs, f"{story} covers nothing"
        assert refs <= set(reqs), f"{story} covers unknown {refs - set(reqs)}"
        covered |= refs
    assert len(story_ids) == len(set(story_ids)), "duplicate story ids"
    assert covered == set(reqs), f"requirements without a story: {set(reqs) - covered}"
    blocks = re.split(r"^## US-", stories.content, flags=re.MULTILINE)[1:]
    for block in blocks:
        assert re.search(r"As an? .+, I want .+, so that ", block), block[:60]
        assert re.search(r"Given .+, when .+, then ", block), block[:60]
    assert_questions_xor_assumptions(project)


def assert_questions_xor_assumptions(project: Any) -> None:
    """No analyst turn produces both questions and assumptions."""
    for turn in AgentTurn.objects.filter(project=project, agent_instance__role="analyst"):
        kinds = {a["kind"] for a in (turn.output or {}).get("artifacts", [])}
        assert not {"questions", "assumptions"} <= kinds, turn.id
        if (turn.output or {}).get("status") == "waiting_answers":
            assert "questions" in kinds


def assert_architecture(project: Any) -> None:
    reqs = requirement_ids(project)
    adrs = of_kind(project, "adr")
    assert len(adrs) >= 2, "at least the stack ADR and the riskiest decision"
    for adr in adrs:
        cited = set(re.findall(r"F-\d{2,3}", adr.content))
        assert cited, f"{adr.name} cites no requirement"
        assert cited <= set(reqs), f"{adr.name} cites unknown {cited - set(reqs)}"
    (stack,) = of_kind(project, "stack")
    assert project.stack == stack.data


def assert_planning(project: Any, roles: set[str]) -> None:
    reqs = requirement_ids(project)
    (board,) = of_kind(project, "task_board")
    tasks = board.data["tasks"]
    assert tasks[0]["external_id"] == "T-01"
    covered = {r for t in tasks for r in t["covers"]["requirements"]}
    assert covered <= set(reqs)
    musts = {r for r, priority in reqs.items() if priority == "must"}
    assert musts <= covered, f"must requirements without a task: {musts - covered}"
    assert {t["assigned_role"] for t in tasks} <= roles
    for proposal in of_kind(project, "team_proposal"):
        ids = {t["external_id"] for t in tasks}
        assert all(set(p["for_tasks"]) <= ids for p in proposal.data["proposals"])


def assert_reviews(project: Any) -> None:
    """Per task: ids R-1..R-n with no gap or reuse; carried findings keep their identity."""
    by_task: dict[str, list[Artifact]] = defaultdict(list)
    for review in Artifact.objects.filter(project=project, kind="review"):
        by_task[review.data["task_id"] + review.name.split("-iter")[0]].append(review)
    for reviews in by_task.values():
        reviews.sort(key=lambda r: r.data["iteration"])
        first_seen: dict[str, int] = {}
        for review in reviews:
            data = review.data
            for finding in data["findings"]:
                seen = first_seen.setdefault(finding["id"], finding["first_seen_iteration"])
                assert seen == finding["first_seen_iteration"], finding["id"]
            open_blocking = sum(
                1
                for f in data["findings"]
                if f["severity"] in {"blocker", "major"} and not f["resolved"]
            )
            assert data["blocking_count"] == open_blocking
            assert (data["verdict"] == "request_changes") == (open_blocking > 0)
        numbers = sorted(int(i[2:]) for i in first_seen)
        assert numbers == list(range(1, len(numbers) + 1)), f"finding ids {numbers}"
        order = sorted(first_seen, key=lambda i: (first_seen[i], int(i[2:])))
        assert [int(i[2:]) for i in order] == numbers, "numbering does not follow iterations"


def assert_responses(project: Any) -> None:
    """A fix iteration's dev_notes answer every finding left open by the previous review."""
    for notes in Artifact.objects.filter(project=project, kind="dev_notes"):
        ref, iteration = re.match(r"dev_notes/(T-\d+)-iter(\d+)", notes.name).groups()
        previous = Artifact.objects.filter(
            project=project, kind="review", name=f"reviews/{ref}-iter{int(iteration) - 1}.md"
        ).first()
        if previous is None:
            continue
        responses = notes.content.split("## Responses", 1)[1].split("## ", 1)[0]
        for finding in previous.data["findings"]:
            if not finding["resolved"]:
                assert finding["id"] in responses, (notes.name, finding["id"])


def assert_test_reports(project: Any) -> None:
    for report in Artifact.objects.filter(project=project, kind="test_report"):
        data = report.data
        assert (data["verdict"] == "pass") == (data["failed"] == 0 and data["exit_code"] == 0)
        if data["scope"] == "integration":
            assert data["command"] == project.stack["test_command"]
        if data["scope"] == "task":
            assert data["task_id"] in report.name


def assert_delivery(project: Any) -> None:
    assert_reviews(project)
    assert_responses(project)
    assert_test_reports(project)
    assert of_kind(project, "release_notes")
    assert of_kind(project, "retrospective")

# SPDX-License-Identifier: AGPL-3.0-or-later
from typing import Any

import pytest
from pydantic import ValidationError
from schema_helpers import DELETE, load_json, patched

from dexterhouse_schema import ARTIFACT_MODELS, STRUCTURED_KINDS, TurnContext, validate_artifact
from dexterhouse_schema.artifacts import TaskBoard, TestReport

EXAMPLES = {kind: load_json(f"artifacts/{kind}.json") for kind in STRUCTURED_KINDS}


def invalid(kind: str, changes: dict[str, Any], match: str, ctx: TurnContext | None = None) -> None:
    with pytest.raises(ValidationError, match=match):
        validate_artifact(kind, patched(EXAMPLES[kind], changes), ctx)


def finding(fid: str, severity: str, first_seen: int, resolved: bool = False) -> dict[str, Any]:
    base = EXAMPLES["review"]["findings"][0]
    return {
        **base,
        "id": fid,
        "severity": severity,
        "first_seen_iteration": first_seen,
        "resolved": resolved,
    }


def test_every_structured_kind_has_a_model() -> None:
    assert set(ARTIFACT_MODELS) == set(STRUCTURED_KINDS)


@pytest.mark.parametrize("kind", STRUCTURED_KINDS)
def test_doc_examples_are_valid(kind: str) -> None:
    assert isinstance(validate_artifact(kind, EXAMPLES[kind]), ARTIFACT_MODELS[kind])


def test_unknown_kind() -> None:
    with pytest.raises(KeyError):
        validate_artifact("requirements", {})


@pytest.mark.parametrize(
    ("changes", "match"),
    [
        ({"test_command": "x" * 301}, "longer than 300"),
        ({"run_command": "a && b && c && d && e"}, "more than 3"),
        ({"install_command": "sudo apt-get install -y libpq"}, "sudo"),
        ({"install_command": "apt-get update && sudo make install"}, "sudo"),
        ({"ports": [80]}, "greater than or equal to 1024"),
        ({"ports": [70000]}, "less than or equal to 65535"),
        ({"services": ["mysql"]}, "services"),
        ({"language": "cobol"}, "language"),
        ({"workspace_image": "ubuntu:latest"}, "workspace_image"),
        ({"package_manager": "poetry"}, "package_manager"),
        ({"healthcheck_path": "api/health"}, "pattern"),
        ({"test_command": ""}, "at least 1"),
    ],
)
def test_invalid_stack(changes: dict[str, Any], match: str) -> None:
    invalid("stack", changes, match)


def test_stack_command_limits_are_inclusive() -> None:
    validate_artifact("stack", patched(EXAMPLES["stack"], {"run_command": "a && b && c && d"}))
    validate_artifact("stack", patched(EXAMPLES["stack"], {"notes": "uses sudoers? no"}))


@pytest.mark.parametrize(
    ("changes", "match"),
    [
        ({"tasks.0.external_id": "T-1"}, "pattern"),
        ({"tasks.1.external_id": "T-01"}, "duplicate external_id"),
        ({"tasks.0.external_id": "T-02", "tasks.1.depends_on": []}, "T-01 is required"),
        ({"tasks.2.depends_on": ["T-01", "T-04"]}, "depends on unknown T-04"),
        ({"tasks.0.depends_on": ["T-05"]}, "cycle"),
        ({"tasks.0.depends_on": ["T-01"]}, "cycle"),
        ({"tasks.0.acceptance": []}, "at least 1"),
        ({"tasks.0.estimate": "XL"}, "estimate"),
        ({"tasks": []}, "at least 1"),
    ],
)
def test_invalid_task_board(changes: dict[str, Any], match: str) -> None:
    invalid("task_board", changes, match)


def test_task_board_limits_and_order() -> None:
    board = validate_artifact("task_board", EXAMPLES["task_board"])
    assert isinstance(board, TaskBoard)
    assert board.topological_order() == ["T-01", "T-03", "T-05"]
    task = EXAMPLES["task_board"]["tasks"][0]
    many = [{**task, "external_id": f"T-{i:03d}", "depends_on": []} for i in range(201)]
    invalid("task_board", {"tasks": many}, "at most 200")


def test_task_board_roles_with_context() -> None:
    ctx = TurnContext(installed_roles=frozenset({"developer"}))
    validate_artifact("task_board", EXAMPLES["task_board"], ctx)
    invalid("task_board", {"tasks.1.assigned_role": "designer"}, "not installed: designer", ctx)


@pytest.mark.parametrize(
    ("changes", "match"),
    [
        ({"proposals": [EXAMPLES["team_proposal"]["proposals"][0]] * 4}, "at most 3"),
        ({"proposals.0.risk": "high"}, "risk"),
        ({"proposals.0.permissions.0.risk": "high"}, "risk"),
        ({"proposals.0.for_tasks": []}, "at least 1"),
        ({"proposals.0.rating": 6}, "less than or equal to 5"),
        ({"installed": ["htmx-frontend-developer"]}, "pattern"),
        ({"marketplace_status": "down"}, "marketplace_status"),
    ],
)
def test_invalid_team_proposal(changes: dict[str, Any], match: str) -> None:
    invalid("team_proposal", changes, match)


def test_team_proposal_metrics_may_be_unknown() -> None:
    """No marketplace site in 1.0: rating and installs are null (or omitted)."""
    proposal = {**EXAMPLES["team_proposal"]["proposals"][0], "rating": None, "installs": None}
    data = {**EXAMPLES["team_proposal"], "proposals": [proposal]}
    validated = validate_artifact("team_proposal", data)
    assert (validated.proposals[0].rating, validated.proposals[0].installs) == (None, None)
    del proposal["rating"], proposal["installs"]
    assert validate_artifact("team_proposal", data).proposals[0].rating is None


def test_team_proposal_tasks_with_context() -> None:
    validate_artifact(
        "team_proposal", EXAMPLES["team_proposal"], TurnContext(task_ids=frozenset({"T-07"}))
    )
    invalid(
        "team_proposal", {}, "not in task board: T-07", TurnContext(task_ids=frozenset({"T-01"}))
    )


@pytest.mark.parametrize(
    ("changes", "match"),
    [
        ({"questions": []}, "at least 1"),
        ({"questions": [EXAMPLES["questions"]["questions"][0]] * 7}, "at most 6"),
        ({"questions": [EXAMPLES["questions"]["questions"][0]] * 2}, "duplicate id"),
        ({"questions.0.id": "Q1"}, "pattern"),
        ({"questions.0.default_assumption": DELETE}, "default_assumption"),
        ({"questions.0.default_assumption": " "}, "pattern"),
        ({"questions.0.options": DELETE}, "requires options"),
        ({"questions.0.kind": "date"}, "kind"),
    ],
)
def test_invalid_questions(changes: dict[str, Any], match: str) -> None:
    invalid("questions", changes, match)


def test_boolean_question_needs_no_options() -> None:
    data = patched(
        EXAMPLES["questions"], {"questions.0.kind": "boolean", "questions.0.options": DELETE}
    )
    validate_artifact("questions", data)


@pytest.mark.parametrize(
    ("changes", "match"),
    [
        ({"assumptions.0.id": "1"}, "pattern"),
        ({"assumptions.0.risk": "none"}, "risk"),
        ({"assumptions": [EXAMPLES["assumptions"]["assumptions"][0]] * 2}, "duplicate id"),
    ],
)
def test_invalid_assumptions(changes: dict[str, Any], match: str) -> None:
    invalid("assumptions", changes, match)


@pytest.mark.parametrize(
    ("changes", "match"),
    [
        ({"blocking_count": 0}, "blocking_count is 0"),
        ({"verdict": "approve"}, "request_changes iff"),
        ({"findings.0.resolved": True}, "blocking_count is 1"),
        ({"findings.0.resolved": True, "blocking_count": 0}, "request_changes iff"),
        ({"findings.0.id": "F-1"}, "pattern"),
        ({"findings": [finding("R-1", "major", 1), finding("R-1", "nit", 1)]}, "duplicate finding"),
        ({"findings.0.request": ""}, "at least 1"),
        ({"findings.0.how_to_verify": "  "}, "pattern"),
        ({"findings.0.first_seen_iteration": 3}, "after iteration"),
        ({"findings.0.severity": "critical"}, "severity"),
        ({"findings.0.line": 0}, "greater than or equal to 1"),
        ({"iteration": 0}, "greater than or equal to 1"),
        ({"verdict": "pass"}, "verdict"),
    ],
)
def test_invalid_review(changes: dict[str, Any], match: str) -> None:
    invalid("review", changes, match)


@pytest.mark.parametrize(
    ("iteration", "findings", "error"),
    [
        (1, [finding("R-1", "nit", 1)], None),
        (2, [finding("R-1", "major", 1), finding("R-2", "minor", 2, resolved=True)], "iteration 2"),
        (2, [finding("R-1", "major", 1), finding("R-2", "nit", 1, resolved=True)], None),
        (2, [finding("R-1", "major", 2)], None),
        (3, [finding("R-1", "major", 3)], "only add blocker"),
        (3, [finding("R-1", "blocker", 3)], None),
        (4, [finding("R-1", "major", 2)], None),
    ],
)
def test_review_iteration_rules(
    iteration: int, findings: list[dict[str, Any]], error: str | None
) -> None:
    blocking = sum(
        1 for f in findings if f["severity"] in {"blocker", "major"} and not f["resolved"]
    )
    data = {
        **EXAMPLES["review"],
        "iteration": iteration,
        "findings": findings,
        "blocking_count": blocking,
        "verdict": "request_changes" if blocking else "approve",
    }
    if error is None:
        validate_artifact("review", data)
    else:
        with pytest.raises(ValidationError, match=error):
            validate_artifact("review", data)


def test_review_known_finding_ids_context() -> None:
    validate_artifact(
        "review", EXAMPLES["review"], TurnContext(known_finding_ids=frozenset({"R-1"}))
    )
    invalid("review", {}, "inconsistent", TurnContext(known_finding_ids=frozenset()))
    data = {"findings.0.first_seen_iteration": 2}
    invalid("review", data, "inconsistent", TurnContext(known_finding_ids=frozenset({"R-1"})))


def test_test_report_verdict_is_recomputed() -> None:
    report = validate_artifact("test_report", patched(EXAMPLES["test_report"], {"verdict": "pass"}))
    assert isinstance(report, TestReport)
    assert report.verdict == "fail"
    assert report.declared_verdict == "pass"
    assert report.verdict_corrected
    passing = {"failed": 0, "exit_code": 0, "failures": [], "verdict": "fail"}
    report = validate_artifact("test_report", patched(EXAMPLES["test_report"], passing))
    assert report.verdict == "pass"
    clean = validate_artifact("test_report", EXAMPLES["test_report"])
    assert not clean.verdict_corrected
    assert clean.declared_verdict == "fail"


@pytest.mark.parametrize(
    ("changes", "match"),
    [
        ({"scope": "smoke", "smoke": DELETE}, "requires `smoke`"),
        ({"failures": [EXAMPLES["test_report"]["failures"][0]] * 51}, "at most 50"),
        ({"report_artifact_id": "not-a-uuid"}, "UUID"),
        ({"failures.0.related_finding": "3"}, "pattern"),
        ({"smoke.status": 42}, "greater than or equal to 100"),
        ({"failed": -1}, "greater than or equal to 0"),
        ({"scope": "unit"}, "scope"),
    ],
)
def test_invalid_test_report(changes: dict[str, Any], match: str) -> None:
    invalid("test_report", changes, match)


def test_integration_command_must_match_stack() -> None:
    ctx = TurnContext(stack_test_command="uv run pytest -q tests/test_bookings.py")
    validate_artifact(
        "test_report", patched(EXAMPLES["test_report"], {"scope": "integration"}), ctx
    )
    other = TurnContext(stack_test_command="uv run pytest -q")
    invalid("test_report", {"scope": "integration"}, "stack.test_command", other)

# SPDX-License-Identifier: AGPL-3.0-or-later
import pytest
from schema_helpers import DELETE, assert_invalid, load_yaml, patched

from dexterhouse_schema import Process

DEFAULT = load_yaml("packages/software-house-default/process.yaml")
REVIEW_ONLY = load_yaml("packages/code-review-only/process.yaml")
PHASES = {p["id"]: i for i, p in enumerate(DEFAULT["phases"])}


def phase(phase_id: str, field: str) -> str:
    return f"phases.{PHASES[phase_id]}.{field}"


def test_software_house_default_is_valid() -> None:
    process = Process.model_validate(DEFAULT)
    assert [p.id for p in process.phases][:3] == ["analysis", "architecture", "planning"]
    assert process.brief_requirements() == {}
    assert process.ancestors("implementation") == {"planning", "architecture", "analysis"}
    implementation = process.phases[PHASES["implementation"]]
    assert [s.agent for s in implementation.step_list()] == ["developer", "reviewer", "tester"]
    planning = process.phases[PHASES["planning"]]
    assert planning.produced_kinds() == {"task_board", "team_proposal"}


def test_code_review_only_requires_stack_in_brief() -> None:
    process = Process.model_validate(REVIEW_ONLY)
    assert process.brief_requirements() == {"stack": ["review"]}
    assert process.phases[0].step_list()[0].agent == "reviewer"


def test_workspace_phase_without_upstream_stack_is_a_requirement() -> None:
    data = patched(DEFAULT, {phase("architecture", "produces"): ["architecture", "adr"]})
    assert Process.model_validate(data).brief_requirements() == {"stack": ["implementation"]}


def test_stack_from_a_sibling_branch_does_not_count() -> None:
    data = patched(DEFAULT, {phase("implementation", "needs"): ["analysis"]})
    assert Process.model_validate(data).brief_requirements() == {"stack": ["implementation"]}


@pytest.mark.parametrize(
    ("changes", "match"),
    [
        ({phase("architecture", "id"): "analysis"}, "duplicate phase id"),
        ({phase("planning", "needs"): ["design"]}, "needs unknown phase"),
        ({phase("analysis", "needs"): ["release"]}, "cycle"),
        ({phase("analysis", "needs"): ["analysis"]}, "cycle"),
        ({phase("analysis", "steps"): ["analyst"]}, "exactly one of"),
        ({phase("analysis", "agent"): DELETE}, "exactly one of"),
        ({phase("planning", "steps"): []}, "at least 1"),
        ({phase("implementation", "max_iterations"): DELETE}, "type loop requires"),
        ({phase("implementation", "over"): DELETE}, "type loop requires"),
        ({phase("implementation", "on_exhausted"): DELETE}, "type loop requires"),
        ({phase("implementation", "max_iterations"): 11}, "less than or equal to 10"),
        ({phase("implementation", "max_iterations"): 0}, "greater than or equal to 1"),
        ({phase("implementation", "on_exhausted"): "retry"}, "on_exhausted"),
        ({phase("implementation", "over"): "tickets"}, "not an artifact kind"),
        ({phase("implementation", "type"): "parallel"}, "type"),
        ({phase("implementation", "type"): DELETE}, "need type loop"),
        ({phase("analysis", "produces"): ["requirements", "poem"]}, "unknown artifact kind"),
        ({phase("planning", "steps.0.produces"): ["plan"]}, "unknown artifact kind"),
        ({phase("analysis", "exit"): "tests_green"}, "exit"),
        ({phase("analysis", "exit"): "command_ok"}, "requires `command`"),
        ({phase("release", "steps.1.command"): DELETE}, "requires `command`"),
        ({phase("analysis", "gate.default"): "always"}, "default"),
        ({phase("planning", "gate.on_approve"): ["push"]}, "on_approve"),
        ({phase("release", "gate.on_reject"): "reopen_analysis"}, "on_reject"),
        ({phase("architecture", "gate.id"): "approve_plan"}, "duplicate gate id"),
        ({phase("planning", "after_gate.0.when"): "sometimes"}, "when"),
        ({phase("planning", "gate"): DELETE}, "after_gate requires a gate"),
        ({phase("release", "steps.0.when"): "always"}, "only allowed in after_gate"),
        ({phase("planning", "steps.0.agent"): "Project Manager"}, "pattern"),
        ({"rooms.design": "meeting_room"}, "unknown phase"),
        ({"phases": []}, "at least 1"),
        ({"version": "1.0"}, "pattern"),
        ({phase("analysis", "owner"): "me"}, "Extra inputs"),
    ],
)
def test_invalid(changes: dict[str, object], match: str) -> None:
    assert_invalid(Process, patched(DEFAULT, changes), match)


def test_when_values() -> None:
    for value in ("hired", "always", "never"):
        Process.model_validate(patched(DEFAULT, {phase("planning", "after_gate.0.when"): value}))

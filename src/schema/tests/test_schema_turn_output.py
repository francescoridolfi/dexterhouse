# SPDX-License-Identifier: AGPL-3.0-or-later
import json
from typing import Any, get_args

import pytest
from pydantic import ValidationError
from schema_helpers import FIXTURES, load_json, patched

from dexterhouse_schema import (
    TurnContext,
    TurnOutput,
    extract_turn_json,
    validate_turn_output,
    validation_messages,
)
from dexterhouse_schema.common import TEXT_KINDS
from dexterhouse_schema.turn_output import TestReportArtifact, TextArtifact

RAW = (FIXTURES / "artifacts/turn_output.json").read_text()
EXAMPLE = json.loads(RAW)
REVIEW = load_json("artifacts/review.json")
TEST_REPORT = load_json("artifacts/test_report.json")


def review_turn(**changes: Any) -> dict[str, Any]:
    turn = {
        "status": "done",
        "summary": "Reviewed T-05 iteration 2.",
        "artifacts": [{"kind": "review", "name": "reviews/T-05-iter2.md", "data": REVIEW}],
        "verdict": "request_changes",
    }
    return {**turn, **changes}


def report_turn(report: dict[str, Any], verdict: str | None) -> dict[str, Any]:
    return {
        "status": "done",
        "summary": "Ran the task tests.",
        "artifacts": [{"kind": "test_report", "name": "tests/T-05-iter2.json", "data": report}],
        "verdict": verdict,
    }


def invalid(data: Any, match: str, ctx: TurnContext | None = None) -> ValidationError:
    with pytest.raises(ValidationError, match=match) as info:
        validate_turn_output(data, ctx)
    return info.value


def test_doc_example_is_valid_from_text_and_mapping() -> None:
    for raw in (RAW, RAW.encode(), EXAMPLE):
        turn = validate_turn_output(raw)
        assert turn.status == "done"
        assert [a.kind for a in turn.artifacts] == ["requirements", "stack"]
        assert turn.handoff is not None
        assert turn.handoff.to_step == "reviewer"
        assert turn.warnings == []


def test_text_kinds_match_the_literal() -> None:
    literal = get_args(TextArtifact.model_fields["kind"].annotation)
    assert set(literal) == set(TEXT_KINDS)


@pytest.mark.parametrize(
    ("changes", "match"),
    [
        ({"status": "finished"}, "status"),
        ({"summary": "x" * 401}, "at most 400"),
        ({"summary": ""}, "at least 1"),
        ({"status": "blocked"}, "blocked_reason is required"),
        ({"status": "blocked", "blocked_reason": "tired"}, "blocked_reason"),
        ({"blocked_reason": "budget"}, "blocked_reason is required iff"),
        ({"verdict": "maybe"}, "verdict"),
        ({"artifacts.0.kind": "poem"}, "does not match any of the expected tags"),
        ({"artifacts.0.data": {}}, "Extra inputs"),
        ({"artifacts.1.content": "# stack"}, "Extra inputs"),
        ({"artifacts.1.data.ports": [22]}, "greater than or equal to 1024"),
        ({"artifacts.0.name": "../requirements.md"}, "'..'"),
        ({"artifacts.0.name": "r" * 201}, "at most 200"),
        ({"handoff.to_step": "Reviewer"}, "pattern"),
        ({"dev_notes": "x"}, "Extra inputs"),
    ],
)
def test_invalid(changes: dict[str, Any], match: str) -> None:
    invalid(patched(EXAMPLE, changes), match)


def test_blocked_turn() -> None:
    data = patched(EXAMPLE, {"status": "blocked", "blocked_reason": "tool_unavailable"})
    assert validate_turn_output(data).blocked_reason == "tool_unavailable"


def test_limits_on_artifacts() -> None:
    text = {"kind": "file", "name": "log.txt", "content": "x"}
    invalid({**EXAMPLE, "artifacts": [text] * 21}, "at most 20")
    big = {**text, "content": "é" * (205 * 1024)}  # two bytes per character
    invalid({**EXAMPLE, "artifacts": [big]}, "limit 409600")
    validate_turn_output({**EXAMPLE, "artifacts": [{**text, "content": "x" * 400 * 1024}]})


def test_review_verdict_must_match() -> None:
    assert validate_turn_output(review_turn()).verdict == "request_changes"
    invalid(review_turn(verdict="approve"), "differs from review verdict")
    invalid(review_turn(verdict=None), "differs from review verdict")


def test_test_report_verdict_must_match_and_is_corrected() -> None:
    assert validate_turn_output(report_turn(TEST_REPORT, "fail")).warnings == []
    invalid(report_turn(TEST_REPORT, "approve"), "differs from test_report verdict")
    lying = patched(TEST_REPORT, {"verdict": "pass"})
    turn = validate_turn_output(report_turn(lying, "pass"))
    assert turn.verdict == "fail"
    artifact = turn.artifacts[0]
    assert isinstance(artifact, TestReportArtifact)
    assert artifact.data.verdict == "fail"
    assert turn.warnings == ["test_report verdict recomputed as 'fail' (declared 'pass')"]
    assert validate_turn_output(report_turn(lying, "fail")).verdict == "fail"


def test_context_allowed_kinds() -> None:
    ctx = TurnContext(allowed_kinds=frozenset({"requirements", "user_stories"}))
    invalid(EXAMPLE, "not in output_contract: stack", ctx)
    ok = TurnContext(allowed_kinds=frozenset({"requirements", "stack"}))
    validate_turn_output(EXAMPLE, ok)


def test_context_verdict_rules() -> None:
    reviewer = TurnContext(verdict="review")
    validate_turn_output(review_turn(), reviewer)
    invalid(EXAMPLE, "verdict is required for this step: approve | request_changes", reviewer)
    tester = TurnContext(verdict="test")
    invalid(review_turn(), "required for this step: fail | pass", tester)
    validate_turn_output(report_turn(TEST_REPORT, "fail"), tester)
    other = TurnContext(verdict="none")
    validate_turn_output(EXAMPLE, other)
    invalid(review_turn(), "only allowed for reviewer and tester", other)


def test_context_waiting_answers_requires_ask() -> None:
    waiting = {**EXAMPLE, "status": "waiting_answers"}
    validate_turn_output(waiting)
    validate_turn_output(waiting, TurnContext(asked=True))
    invalid(waiting, "project.ask", TurnContext(asked=False))


def test_context_reaches_nested_artifacts() -> None:
    ctx = TurnContext(known_finding_ids=frozenset())
    invalid(review_turn(), "inconsistent with previous reviews", ctx)


def test_validation_messages_are_flat() -> None:
    try:
        validate_turn_output(patched(EXAMPLE, {"artifacts.1.data.ports": [22], "summary": ""}))
    except ValidationError as exc:
        messages = validation_messages(exc)
    assert "summary: String should have at least 1 character" in messages
    assert any(m.startswith("artifacts[1].stack.data.ports[0]: ") for m in messages)


def test_extract_turn_json_discards_free_text() -> None:
    message = f"I am done, here is the result {{not json}}:\n```json\n{RAW}\n```\n"
    assert extract_turn_json(message) == EXAMPLE
    assert extract_turn_json(RAW) == EXAMPLE
    for bad in ("no json here", '{"a": 1} trailing text', "[1, 2]"):
        with pytest.raises(ValueError, match="does not end with a JSON object"):
            extract_turn_json(bad)


def test_model_validate_without_context() -> None:
    assert TurnOutput.model_validate(EXAMPLE).summary.startswith("Produced")

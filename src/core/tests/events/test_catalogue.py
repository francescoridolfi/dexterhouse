# SPDX-License-Identifier: AGPL-3.0-or-later
"""Event catalogue: registry completeness and payload validation (pure pydantic, no DB)."""

import re
import uuid
from decimal import Decimal

import pytest
from pydantic import ValidationError

from dexterhouse.apps.events.schemas import EVENT_TYPES, payload_model

# Rows of the five family tables in dev_docs/01_architecture/contracts/events/, one per type.
EXPECTED_PER_FAMILY = {
    "project_process": 24,
    "agents": 14,
    "tasks_gates": 14,
    "workspace_release": 15,
    "packages_budget_security": 17,
}
TYPE_NAME = re.compile(r"^[a-z_]+(\.[a-z_]+)+$")


def _id() -> str:
    return str(uuid.uuid4())


def _family(model: type) -> str:
    return model.__module__.rsplit(".", 1)[-1]


def test_catalogue_size() -> None:
    assert len(EVENT_TYPES) == sum(EXPECTED_PER_FAMILY.values()) == 84


def test_catalogue_size_per_family() -> None:
    counts: dict[str, int] = {}
    for model in EVENT_TYPES.values():
        counts[_family(model)] = counts.get(_family(model), 0) + 1
    assert counts == EXPECTED_PER_FAMILY


@pytest.mark.parametrize("event_type", sorted(EVENT_TYPES))
def test_type_names_and_actors(event_type: str) -> None:
    model = EVENT_TYPES[event_type]
    assert TYPE_NAME.match(event_type)
    assert model.event_type == event_type
    assert model.schema_version == 1
    assert model.actors
    assert set(model.actors) <= {"agent", "user", "system"}


def test_only_agent_speaking_is_stream_only() -> None:
    assert [t for t, m in EVENT_TYPES.items() if not m.persisted] == ["agent.speaking"]


ARTIFACT = {"id": _id(), "kind": "review", "version": 2}

VALID = {
    "project.created": {
        "name": "GymBook",
        "execution_mode": "supervised",
        "budget": "25.00",
        "process": {"name": "software-house-default", "version": "1.0.0"},
    },
    "process.started": {"phases": [{"id": "analysis", "needs": [], "room": "meeting_room"}]},
    "phase.failed": {"phase_id": "analysis"},
    "agent.turn.completed": {
        "turn_id": _id(),
        "agent_id": _id(),
        "duration_s": 12.5,
        "input_tokens": 1200,
        "output_tokens": 300,
        "cached_tokens": 0,
        "cost": "0.012345",
        "tool_calls": 3,
        "artifacts": [ARTIFACT],
    },
    "agent.speaking": {"turn_id": _id(), "agent_id": _id(), "text": "Hello", "seq": 1},
    "task.step.completed": {
        "task_id": _id(),
        "step": "reviewer",
        "agent_id": _id(),
        "verdict": "request_changes",
        "artifact": ARTIFACT,
    },
    "gate.decided": {
        "gate_id": _id(),
        "type": "approval",
        "decision": "approve",
        "decided_by": None,
        "auto": True,
        "next": "phase_completed",
    },
    "test.run.completed": {
        "scope": "integration",
        "passed": 10,
        "failed": 0,
        "skipped": 1,
        "duration_s": 4.2,
        "ok": True,
        "report_artifact": {"id": _id(), "version": 1},
    },
    "workspace.idle": {},
    "package.installed": {
        "package_id": _id(),
        "version_id": _id(),
        "name": "developer",
        "version": "1.2.0",
        "kind": "agent",
    },
    "budget.org_exceeded": {"spent_month": "100.5", "budget_monthly": "100"},
}


@pytest.mark.parametrize("event_type", sorted(VALID))
def test_valid_examples(event_type: str) -> None:
    model = payload_model(event_type)
    payload = model.model_validate(VALID[event_type])
    assert model.model_validate(payload.model_dump(mode="json")) == payload


def test_valid_examples_cover_every_family() -> None:
    assert {_family(EVENT_TYPES[t]) for t in VALID} == set(EXPECTED_PER_FAMILY)


def test_money_is_decimal_and_defaults() -> None:
    created = payload_model("project.created").model_validate(VALID["project.created"])
    assert created.budget == Decimal("25.00")
    installed = payload_model("package.installed").model_validate(VALID["package.installed"])
    assert installed.roles == []


INVALID = [
    (
        "agent.turn.completed",
        {k: v for k, v in VALID["agent.turn.completed"].items() if k != "cost"},
    ),
    ("task.step.completed", {**VALID["task.step.completed"], "verdict": "maybe"}),
    ("project.created", {**VALID["project.created"], "execution_mode": "manual"}),
    ("gate.decided", {k: v for k, v in VALID["gate.decided"].items() if k != "decided_by"}),
    ("package.installed", {**VALID["package.installed"], "unexpected": 1}),
    ("process.started", {"phases": [{"id": "analysis", "needs": [], "room": "x", "extra": 1}]}),
    ("agent.speaking", {**VALID["agent.speaking"], "agent_id": "not-a-uuid"}),
    ("workspace.idle", {"reason": "inactive"}),
]


@pytest.mark.parametrize(("event_type", "data"), INVALID)
def test_invalid_examples(event_type: str, data: dict) -> None:
    with pytest.raises(ValidationError):
        payload_model(event_type).model_validate(data)


def test_result_excerpt_is_capped() -> None:
    data = {
        "turn_id": _id(),
        "tool": "workspace.exec",
        "call_seq": 1,
        "allowed": True,
        "duration_ms": 120,
        "result_excerpt": "x" * 501,
    }
    with pytest.raises(ValidationError):
        payload_model("agent.tool.used").model_validate(data)

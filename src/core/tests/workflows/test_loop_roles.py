# SPDX-License-Identifier: AGPL-3.0-or-later
"""Where a task enters the implementation loop, by its assigned role."""

from types import SimpleNamespace

import pytest

from dexterhouse.apps.workflows.engine.loop import first_step
from dexterhouse.apps.workflows.runner import verdict_rule
from dexterhouse_schema.process import Phase

LOOP = Phase.model_validate(
    {
        "id": "implementation",
        "needs": ["planning"],
        "type": "loop",
        "over": "task_board",
        "steps": ["developer", "reviewer", "tester"],
        "max_iterations": 3,
        "on_exhausted": "escalate",
    }
)


@pytest.mark.parametrize(
    ("role", "index", "rule"),
    [("developer", 0, "none"), ("tester", 2, "test"), ("analyst", 0, "none")],
)
def test_task_starts_at_its_role_step(role, index, rule):
    assert first_step(LOOP, SimpleNamespace(assigned_role=role)) == index
    assert verdict_rule(LOOP.step_list()[index].agent) == rule

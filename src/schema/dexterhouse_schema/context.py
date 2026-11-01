# SPDX-License-Identifier: AGPL-3.0-or-later
"""Runtime context for rules that depend on the step being validated.

Pass it as pydantic validation context under the key ``"turn"``::

    TurnOutput.model_validate(data, context={"turn": TurnContext(...)})

or use :func:`dexterhouse_schema.turn_output.validate_turn_output`. Every field defaults
to ``None``, meaning "unknown: skip the check".
"""

from dataclasses import dataclass
from typing import Literal

from pydantic import ValidationInfo

#: `review`: verdict required, approve | request_changes; `test`: required, pass | fail;
#: `none`: verdict forbidden.
VerdictRule = Literal["review", "test", "none"]


@dataclass(frozen=True)
class TurnContext:
    """What the core knows about the step that produced the output."""

    allowed_kinds: frozenset[str] | None = None
    """`output_contract.artifacts` of the agent."""
    verdict: VerdictRule | None = None
    """Whether the step is a reviewer or tester step."""
    asked: bool | None = None
    """Whether a `project.ask` call succeeded in this turn."""
    known_finding_ids: frozenset[str] | None = None
    """Review finding ids used in previous iterations of the task."""
    installed_roles: frozenset[str] | None = None
    """Roles installed in the organization (task_board `assigned_role`)."""
    task_ids: frozenset[str] | None = None
    """`external_id`s of the current task board (team_proposal `for_tasks`)."""
    stack_test_command: str | None = None
    """`stack.test_command` (integration test_report `command`)."""


EMPTY_CONTEXT = TurnContext()


def turn_context(info: ValidationInfo) -> TurnContext:
    """The :class:`TurnContext` in the validation context, or an empty one."""
    ctx = info.context.get("turn") if isinstance(info.context, dict) else None
    return ctx if isinstance(ctx, TurnContext) else EMPTY_CONTEXT

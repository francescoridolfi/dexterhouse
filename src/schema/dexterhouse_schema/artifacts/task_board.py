# SPDX-License-Identifier: AGPL-3.0-or-later
"""`task_board`: tasks produced by the project manager (a DAG on `depends_on`)."""

from typing import Annotated, Literal

from pydantic import Field, ValidationInfo, model_validator

from dexterhouse_schema.common import Ident, NonEmptyStr, StrictModel, TaskId
from dexterhouse_schema.context import turn_context

MAX_TASKS = 200


class Covers(StrictModel):
    requirements: list[str] = Field(default_factory=list)
    stories: list[str] = Field(default_factory=list)


class BoardTask(StrictModel):
    external_id: TaskId
    title: NonEmptyStr
    description: str
    acceptance: Annotated[list[NonEmptyStr], Field(min_length=1)]
    depends_on: list[TaskId] = Field(default_factory=list)
    estimate: Literal["S", "M", "L"]
    assigned_role: Ident = Field(description="Must be installed (checked with TurnContext).")
    files_hint: list[str] = Field(default_factory=list)
    covers: Covers = Covers()


class TaskBoard(StrictModel):
    tasks: Annotated[list[BoardTask], Field(min_length=1, max_length=MAX_TASKS)]
    notes: str | None = None

    @model_validator(mode="after")
    def _check(self, info: ValidationInfo) -> "TaskBoard":
        ids = [t.external_id for t in self.tasks]
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        if dupes:
            raise ValueError(f"duplicate external_id(s): {', '.join(dupes)}")
        if "T-01" not in ids:
            raise ValueError("task T-01 is required")
        known = set(ids)
        for task in self.tasks:
            missing = sorted(set(task.depends_on) - known)
            if missing:
                raise ValueError(f"{task.external_id} depends on unknown {', '.join(missing)}")
        self._check_acyclic()
        roles = turn_context(info).installed_roles
        if roles is not None:
            unknown = sorted({t.assigned_role for t in self.tasks} - roles)
            if unknown:
                raise ValueError(f"assigned_role not installed: {', '.join(unknown)}")
        return self

    def _check_acyclic(self) -> None:
        _, blocked = _kahn(self.tasks)
        if blocked:
            raise ValueError(f"depends_on has a cycle among {', '.join(sorted(blocked))}")

    def topological_order(self) -> list[str]:
        """Task ids in dependency order (ties keep board order)."""
        return _kahn(self.tasks)[0]


def _kahn(tasks: list[BoardTask]) -> tuple[list[str], set[str]]:
    """Kahn's algorithm: (scheduled ids, ids on or behind a cycle)."""
    pending = {t.external_id: set(t.depends_on) for t in tasks}
    order: list[str] = []
    while ready := [tid for tid, deps in pending.items() if not deps]:
        order.extend(ready)
        for tid in ready:
            del pending[tid]
        for deps in pending.values():
            deps.difference_update(ready)
    return order, set(pending)

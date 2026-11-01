# SPDX-License-Identifier: AGPL-3.0-or-later
"""`TurnInputs`: the work order the workflow engine (E-02) gives to a turn.

Everything the context builder needs that lives outside this app (artifacts, task, gate
answers, notes, workspace tree) arrives as data, so the agents runtime does not depend on
the projects and workflows models. See `docs/README.md` in this app.
"""

import uuid
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ArtifactInput(_Model):
    """An artifact declared by the phase (`inputs`); Markdown `content` or structured `data`."""

    id: uuid.UUID
    kind: str
    name: str
    version: int = 1
    content: str | None = None
    data: Any = None
    untrusted: bool = False


class TaskInput(_Model):
    external_id: str | None = None  # `T-05`
    title: str
    description: str = ""
    acceptance: list[str] = Field(default_factory=list)
    iteration: int | None = None
    max_iterations: int | None = None
    files_hint: list[str] = Field(default_factory=list)
    status: str | None = None


class NoteInput(_Model):
    id: uuid.UUID
    text: str


class TurnInputs(_Model):
    """Section inputs of the context builder (agents/context_builder.md, sections 6-12)."""

    step_description: str = ""
    task: TaskInput | None = None
    gate_answers: list[str] = Field(default_factory=list, description="Most recent first.")
    review_items: list[dict[str, Any]] = Field(
        default_factory=list, description="Open findings (`resolved: false`) or test failures."
    )
    artifacts: list[ArtifactInput] = Field(default_factory=list, description="Phase order.")
    notes: list[NoteInput] = Field(default_factory=list, description="Most recent first.")
    workspace_tree: str | None = None
    memory_query: str | None = None
    room: str | None = None
    mode: Literal["supervised", "autonomous"] = "supervised"
    may_ask: bool = False
    data_residency: Literal["any", "local"] = "any"
    verdict_rule: Literal["review", "test", "none"] | None = None
    known_finding_ids: list[str] | None = None
    installed_roles: list[str] | None = None
    task_ids: list[str] | None = None
    stack_test_command: str | None = None

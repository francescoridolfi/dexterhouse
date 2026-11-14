# SPDX-License-Identifier: AGPL-3.0-or-later
"""Schemas of the structured artifact kinds (the `data` of a TurnOutput artifact)."""

from typing import Any

from pydantic import BaseModel

from dexterhouse_schema.artifacts.code_graph import CodeGraph
from dexterhouse_schema.artifacts.questions import Assumptions, Questions
from dexterhouse_schema.artifacts.review import Review
from dexterhouse_schema.artifacts.stack import Stack
from dexterhouse_schema.artifacts.task_board import TaskBoard
from dexterhouse_schema.artifacts.team_proposal import TeamProposal
from dexterhouse_schema.artifacts.test_report import TestReport
from dexterhouse_schema.context import TurnContext

ARTIFACT_MODELS: dict[str, type[BaseModel]] = {
    "stack": Stack,
    "task_board": TaskBoard,
    "team_proposal": TeamProposal,
    "questions": Questions,
    "assumptions": Assumptions,
    "review": Review,
    "test_report": TestReport,
    "code_graph": CodeGraph,
}


def validate_artifact(kind: str, data: Any, context: TurnContext | None = None) -> BaseModel:
    """Validate `data` against the schema of a structured `kind`.

    Raises:
        KeyError: `kind` is not a structured kind.
        pydantic.ValidationError: `data` does not match.
    """
    model = ARTIFACT_MODELS[kind]
    return model.model_validate(data, context={"turn": context or TurnContext()})


__all__ = [
    "ARTIFACT_MODELS",
    "Assumptions",
    "CodeGraph",
    "Questions",
    "Review",
    "Stack",
    "TaskBoard",
    "TeamProposal",
    "TestReport",
    "validate_artifact",
]

# SPDX-License-Identifier: AGPL-3.0-or-later
"""`questions` (supervised) and `assumptions` (autonomous) produced during analysis."""

from typing import Annotated, Literal

from pydantic import Field, StringConstraints, model_validator

from dexterhouse_schema.common import NonEmptyStr, StrictModel


class Question(StrictModel):
    id: Annotated[str, StringConstraints(pattern=r"^q\d+$")]
    text: NonEmptyStr
    kind: Literal["text", "choice", "boolean"]
    options: list[NonEmptyStr] | None = Field(default=None, description="Required for choice.")
    why: str
    default_assumption: NonEmptyStr

    @model_validator(mode="after")
    def _check_options(self) -> "Question":
        if self.kind == "choice" and not self.options:
            raise ValueError(f"{self.id}: kind choice requires options")
        return self


def _unique_ids(ids: list[str]) -> None:
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    if dupes:
        raise ValueError(f"duplicate id(s): {', '.join(dupes)}")


class Questions(StrictModel):
    questions: Annotated[list[Question], Field(min_length=1, max_length=6)]

    @model_validator(mode="after")
    def _check(self) -> "Questions":
        _unique_ids([q.id for q in self.questions])
        return self


class Assumption(StrictModel):
    id: Annotated[str, StringConstraints(pattern=r"^a\d+$")]
    question: NonEmptyStr
    assumed: NonEmptyStr
    rationale: str
    risk: Literal["low", "medium", "high"]


class Assumptions(StrictModel):
    assumptions: list[Assumption]

    @model_validator(mode="after")
    def _check(self) -> "Assumptions":
        _unique_ids([a.id for a in self.assumptions])
        return self

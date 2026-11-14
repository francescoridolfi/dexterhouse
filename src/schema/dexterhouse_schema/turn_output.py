# SPDX-License-Identifier: AGPL-3.0-or-later
"""`TurnOutput`: the JSON object that ends every agent turn (CD-030).

Context-free rules are always enforced. Rules that depend on the step (allowed kinds,
verdict required or forbidden, `project.ask` called, ...) are enforced only when a
:class:`~dexterhouse_schema.context.TurnContext` is given, see :func:`validate_turn_output`.
"""

import json
from collections.abc import Mapping
from typing import Annotated, Any, Literal

from pydantic import Field, PrivateAttr, StringConstraints, ValidationInfo, model_validator

from dexterhouse_schema.artifacts import (
    Assumptions,
    Questions,
    Review,
    Stack,
    TaskBoard,
    TeamProposal,
    TestReport,
)
from dexterhouse_schema.common import Ident, RelPath, StrictModel
from dexterhouse_schema.context import TurnContext, turn_context

MAX_ARTIFACTS = 20
MAX_CONTENT_BYTES = 400 * 1024

ArtifactName = Annotated[RelPath, StringConstraints(max_length=200)]
Status = Literal["done", "waiting_answers", "blocked"]
TurnVerdict = Literal["approve", "request_changes", "pass", "fail"]
BlockedReason = Literal[
    "missing_input", "tool_unavailable", "permission_denied", "out_of_scope", "budget"
]
_VERDICTS: dict[str, frozenset[str]] = {
    "review": frozenset({"approve", "request_changes"}),
    "test": frozenset({"pass", "fail"}),
}


class TextArtifact(StrictModel):
    """Markdown artifact following the templates (`content`)."""

    kind: Literal[
        "brief",
        "requirements",
        "user_stories",
        "architecture",
        "adr",
        "dev_notes",
        "release_notes",
        "retrospective",
        "file",
    ]
    name: ArtifactName
    content: str


class StackArtifact(StrictModel):
    kind: Literal["stack"]
    name: ArtifactName
    data: Stack


class TaskBoardArtifact(StrictModel):
    kind: Literal["task_board"]
    name: ArtifactName
    data: TaskBoard


class TeamProposalArtifact(StrictModel):
    kind: Literal["team_proposal"]
    name: ArtifactName
    data: TeamProposal


class QuestionsArtifact(StrictModel):
    kind: Literal["questions"]
    name: ArtifactName
    data: Questions


class AssumptionsArtifact(StrictModel):
    kind: Literal["assumptions"]
    name: ArtifactName
    data: Assumptions


class ReviewArtifact(StrictModel):
    kind: Literal["review"]
    name: ArtifactName
    data: Review


class TestReportArtifact(StrictModel):
    __test__ = False  # not a pytest test class

    kind: Literal["test_report"]
    name: ArtifactName
    data: TestReport


Artifact = Annotated[
    TextArtifact
    | StackArtifact
    | TaskBoardArtifact
    | TeamProposalArtifact
    | QuestionsArtifact
    | AssumptionsArtifact
    | ReviewArtifact
    | TestReportArtifact,
    Field(discriminator="kind"),
]


class Handoff(StrictModel):
    to_step: Ident
    notes: str | None = None


class TurnOutput(StrictModel):
    """End-of-turn contract. See the module docstring for context-dependent rules."""

    status: Status
    summary: Annotated[str, StringConstraints(min_length=1, max_length=400)]
    artifacts: Annotated[list[Artifact], Field(max_length=MAX_ARTIFACTS)] = Field(
        default_factory=list
    )
    verdict: TurnVerdict | None = Field(default=None, description="Reviewer/tester steps only.")
    handoff: Handoff | None = None
    blocked_reason: BlockedReason | None = Field(default=None, description="Iff blocked.")
    assumptions_made: list[str] = Field(default_factory=list)
    _warnings: list[str] = PrivateAttr(default_factory=list)

    @property
    def warnings(self) -> list[str]:
        """Non-fatal `output_contract` warnings (e.g. a corrected test_report verdict)."""
        return list(self._warnings)

    @model_validator(mode="after")
    def _check(self, info: ValidationInfo) -> "TurnOutput":
        if (self.status == "blocked") != (self.blocked_reason is not None):
            raise ValueError("blocked_reason is required iff status is blocked")
        size = sum(_artifact_bytes(a) for a in self.artifacts)
        if size > MAX_CONTENT_BYTES:
            raise ValueError(f"artifacts total {size} bytes, limit {MAX_CONTENT_BYTES}")
        ctx = turn_context(info)
        # Kinds first: an artifact the agent may not produce must be reported as such, not
        # through a verdict mismatch it cannot fix (e.g. a developer's test_report).
        self._check_allowed_kinds(ctx)
        self._check_verdict_artifacts(ctx)
        self._check_artifact_verdicts()
        self._check_context(ctx)
        return self

    def _check_allowed_kinds(self, ctx: TurnContext) -> None:
        if ctx.allowed_kinds is not None:
            bad = sorted({a.kind for a in self.artifacts} - ctx.allowed_kinds)
            if bad:
                raise ValueError(f"artifact kind(s) not in output_contract: {', '.join(bad)}")

    def _check_verdict_artifacts(self, ctx: TurnContext) -> None:
        """A step without a verdict cannot carry a review or test_report (it has one)."""
        if ctx.verdict != "none":
            return
        kinds = sorted({a.kind for a in self.artifacts if a.kind in {"review", "test_report"}})
        if kinds:
            raise ValueError(
                f"this step gives no verdict, so it cannot include {' or '.join(kinds)} "
                "artifacts: remove them and keep verdict null"
            )

    def _check_artifact_verdicts(self) -> None:
        for artifact in self.artifacts:
            if isinstance(artifact, ReviewArtifact) and artifact.data.verdict != self.verdict:
                raise ValueError(
                    f"verdict {self.verdict!r} differs from the review verdict "
                    f"{artifact.data.verdict!r}: set the top-level verdict to "
                    f"{artifact.data.verdict!r}"
                )
            if isinstance(artifact, TestReportArtifact):
                report = artifact.data
                if self.verdict not in {report.declared_verdict, report.verdict}:
                    raise ValueError(
                        f"verdict {self.verdict!r} differs from the test_report verdict "
                        f"{report.verdict!r}: set the top-level verdict to {report.verdict!r}"
                    )
                if report.verdict_corrected or self.verdict != report.verdict:
                    self._warnings.append(
                        f"test_report verdict recomputed as {report.verdict!r} "
                        f"(declared {report.declared_verdict!r})"
                    )
                    self.verdict = report.verdict

    def _check_context(self, ctx: TurnContext) -> None:
        if ctx.verdict == "none" and self.verdict is not None:
            raise ValueError("verdict is only allowed for reviewer and tester steps")
        if ctx.verdict in _VERDICTS and self.verdict not in _VERDICTS[ctx.verdict]:
            allowed = " | ".join(sorted(_VERDICTS[ctx.verdict]))
            raise ValueError(f"verdict is required for this step: {allowed}")
        if ctx.asked is False and self.status == "waiting_answers":
            raise ValueError("status waiting_answers requires a successful project.ask call")


def _artifact_bytes(artifact: Any) -> int:
    if isinstance(artifact, TextArtifact):
        return len(artifact.content.encode())
    return len(artifact.data.model_dump_json())


def validate_turn_output(
    raw: str | bytes | Mapping[str, Any], context: TurnContext | None = None
) -> TurnOutput:
    """Validate a TurnOutput given as JSON text or as an already decoded mapping.

    Raises:
        pydantic.ValidationError: with every violated rule (the core reprompts with them).
    """
    ctx = {"turn": context or TurnContext()}
    if isinstance(raw, str | bytes):
        return TurnOutput.model_validate_json(raw, context=ctx)
    return TurnOutput.model_validate(dict(raw), context=ctx)


def extract_turn_json(message: str) -> Any:
    """Return the JSON object that ends `message`, discarding free text before it.

    Trailing whitespace and a closing Markdown code fence are tolerated.

    Raises:
        ValueError: no JSON object ends the message.
    """
    tail = message.rstrip()
    if tail.endswith("```"):
        tail = tail[:-3].rstrip()
    decoder = json.JSONDecoder()
    start = tail.find("{")
    while start != -1:
        try:
            value, end = decoder.raw_decode(tail, start)
        except json.JSONDecodeError:
            value, end = None, -1
        if end == len(tail) and isinstance(value, dict):
            return value
        start = tail.find("{", start + 1)
    raise ValueError("the message does not end with a JSON object")

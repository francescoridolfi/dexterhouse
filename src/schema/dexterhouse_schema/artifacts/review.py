# SPDX-License-Identifier: AGPL-3.0-or-later
"""`review`: reviewer output for one task iteration."""

from typing import Annotated, Literal

from pydantic import Field, StringConstraints, ValidationInfo, model_validator

from dexterhouse_schema.common import NonEmptyStr, StrictModel, TaskId
from dexterhouse_schema.context import turn_context

Severity = Literal["blocker", "major", "minor", "nit"]
BLOCKING_SEVERITIES: frozenset[str] = frozenset({"blocker", "major"})


class Finding(StrictModel):
    id: Annotated[str, StringConstraints(pattern=r"^R-\d+$")]
    severity: Severity
    file: NonEmptyStr
    line: Annotated[int, Field(ge=1)] | None = None
    symbol: str | None = None
    title: NonEmptyStr
    request: NonEmptyStr
    how_to_verify: NonEmptyStr
    resolved: bool
    first_seen_iteration: Annotated[int, Field(ge=1)]


class Review(StrictModel):
    """Review artifact.

    Iteration rules (new finding = `first_seen_iteration == iteration`, or an id not in
    ``TurnContext.known_finding_ids`` when given): iteration 2 adds no `minor`/`nit`
    finding, iteration >= 3 adds only `blocker` findings.
    """

    task_id: TaskId
    iteration: Annotated[int, Field(ge=1)]
    verdict: Literal["approve", "request_changes"]
    summary: str
    findings: list[Finding] = Field(default_factory=list)
    blocking_count: Annotated[int, Field(ge=0)]
    out_of_scope_notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check(self, info: ValidationInfo) -> "Review":
        ids = [f.id for f in self.findings]
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        if dupes:
            raise ValueError(f"duplicate finding id(s): {', '.join(dupes)}")
        blocking = sum(
            1 for f in self.findings if f.severity in BLOCKING_SEVERITIES and not f.resolved
        )
        if self.blocking_count != blocking:
            raise ValueError(
                f"blocking_count is {self.blocking_count} but {blocking} open blocker/major "
                "finding(s) are listed"
            )
        if (self.verdict == "request_changes") != (blocking >= 1):
            raise ValueError("verdict must be request_changes iff blocking_count >= 1")
        self._check_iterations(turn_context(info).known_finding_ids)
        return self

    def _check_iterations(self, known: frozenset[str] | None) -> None:
        for finding in self.findings:
            if finding.first_seen_iteration > self.iteration:
                raise ValueError(f"{finding.id}: first_seen_iteration after iteration")
            is_new = finding.first_seen_iteration == self.iteration
            if known is not None:
                if is_new == (finding.id in known):
                    raise ValueError(
                        f"{finding.id}: first_seen_iteration inconsistent with previous reviews"
                    )
            if not is_new:
                continue
            if self.iteration == 2 and finding.severity in {"minor", "nit"}:
                raise ValueError(f"{finding.id}: iteration 2 cannot add minor/nit findings")
            if self.iteration >= 3 and finding.severity != "blocker":
                raise ValueError(f"{finding.id}: iteration >= 3 can only add blocker findings")

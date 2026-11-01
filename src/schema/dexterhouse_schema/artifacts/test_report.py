# SPDX-License-Identifier: AGPL-3.0-or-later
"""`test_report`: tester output (informative: the core re-runs `test_command`)."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, PrivateAttr, ValidationInfo, model_validator

from dexterhouse_schema.common import HttpUrl, NonEmptyStr, StrictModel, TaskId
from dexterhouse_schema.context import turn_context

MAX_FAILURES = 50
Verdict = Literal["pass", "fail"]


class Failure(StrictModel):
    test: NonEmptyStr
    message: str
    probable_cause: str | None = None
    related_finding: Annotated[str, Field(pattern=r"^R-\d+$")] | None = None


class Smoke(StrictModel):
    url: HttpUrl
    status: Annotated[int, Field(ge=100, le=599)]
    startup_s: Annotated[float, Field(ge=0)]


class TestReport(StrictModel):
    """Test report.

    `verdict` is recomputed (`pass` iff `failed == 0` and `exit_code == 0`) and
    overwritten when inconsistent; the declared value stays in :attr:`declared_verdict`
    and :attr:`verdict_corrected` tells the core to log an `output_contract` warning.
    """

    __test__ = False  # not a pytest test class

    scope: Literal["task", "integration", "smoke"]
    task_id: TaskId | None = None
    iteration: Annotated[int, Field(ge=1)] | None = None
    command: NonEmptyStr
    exit_code: int
    passed: Annotated[int, Field(ge=0)]
    failed: Annotated[int, Field(ge=0)]
    skipped: Annotated[int, Field(ge=0)]
    duration_s: Annotated[float, Field(ge=0)]
    verdict: Verdict
    failures: Annotated[list[Failure], Field(max_length=MAX_FAILURES)] = Field(default_factory=list)
    skipped_reasons: list[str] = Field(default_factory=list)
    coverage_notes: str | None = None
    smoke: Smoke | None = None
    report_artifact_id: Annotated[UUID, Field(strict=False)] | None = None
    _declared_verdict: Verdict | None = PrivateAttr(default=None)

    @property
    def declared_verdict(self) -> Verdict:
        """The verdict written by the agent, before any correction."""
        return self._declared_verdict or self.verdict

    @property
    def verdict_corrected(self) -> bool:
        return self.declared_verdict != self.verdict

    @model_validator(mode="after")
    def _check(self, info: ValidationInfo) -> "TestReport":
        if self.scope == "smoke" and self.smoke is None:
            raise ValueError("scope smoke requires `smoke`")
        expected = turn_context(info).stack_test_command
        if self.scope == "integration" and expected is not None and self.command != expected:
            raise ValueError(f"integration command must be stack.test_command ({expected!r})")
        computed: Verdict = "pass" if self.failed == 0 and self.exit_code == 0 else "fail"
        if computed != self.verdict:
            self._declared_verdict = self.verdict
            self.verdict = computed
        return self

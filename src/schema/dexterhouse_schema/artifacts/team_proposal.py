# SPDX-License-Identifier: AGPL-3.0-or-later
"""`team_proposal`: packages the recruiter proposes to install."""

from typing import Annotated, Literal

from pydantic import Field, StringConstraints, ValidationInfo, model_validator

from dexterhouse_schema.common import (
    PACKAGE_NAME_PATTERN,
    GithubUser,
    Ident,
    PackageName,
    PermissionId,
    SemVer,
    StrictModel,
    TaskId,
)
from dexterhouse_schema.context import turn_context
from dexterhouse_schema.semver import SEMVER_PATTERN

MAX_PROPOSALS = 3
# `name@version`, e.g. `htmx-frontend-developer@1.3.0`.
_PINNED = rf"{PACKAGE_NAME_PATTERN[:-1]}@{SEMVER_PATTERN[1:]}"


class ProposedPermission(StrictModel):
    id: PermissionId
    risk: Literal["low", "medium"] = Field(description="High-risk packages cannot be proposed.")


class Proposal(StrictModel):
    name: PackageName
    version: SemVer
    role: Ident
    reason: str
    for_tasks: Annotated[list[TaskId], Field(min_length=1)]
    permissions: list[ProposedPermission] = Field(default_factory=list)
    risk: Literal["low", "medium"]
    verified: bool
    rating: Annotated[float, Field(ge=0, le=5)]
    installs: Annotated[int, Field(ge=0)]
    author_github: GithubUser


class TeamProposal(StrictModel):
    marketplace_status: Literal["reachable", "unreachable", "degraded"]
    proposals: Annotated[list[Proposal], Field(max_length=MAX_PROPOSALS)]
    installed: list[Annotated[str, StringConstraints(pattern=_PINNED)]] = Field(
        default_factory=list
    )
    summary: str

    @model_validator(mode="after")
    def _check_tasks(self, info: ValidationInfo) -> "TeamProposal":
        task_ids = turn_context(info).task_ids
        if task_ids is not None:
            for proposal in self.proposals:
                unknown = sorted(set(proposal.for_tasks) - task_ids)
                if unknown:
                    raise ValueError(
                        f"{proposal.name}: for_tasks not in task board: {', '.join(unknown)}"
                    )
        return self

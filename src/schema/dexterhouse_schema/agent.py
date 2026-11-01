# SPDX-License-Identifier: AGPL-3.0-or-later
"""`agent.yaml`: definition of an agent package.

Checks that need the core (tool catalog, role uniqueness in the organization) are not
done here; file existence and prompt contents are checked by :mod:`dexterhouse_schema.package`.
"""

import re
from typing import Annotated, Any, Literal

from pydantic import Field, StringConstraints, model_validator

from dexterhouse_schema.common import (
    ARTIFACT_KINDS,
    STRUCTURED_KINDS,
    ExtensibleModel,
    Ident,
    PackageName,
    PermissionId,
    RelPath,
    SchemaVersion,
    StrictModel,
)

#: Keywords of the JSON Schema subset accepted in `args_policy` (applied by the tool gateway).
ARGS_POLICY_KEYWORDS: frozenset[str] = frozenset(
    {"const", "enum", "pattern", "maxLength", "minimum", "maximum"}
)

#: Values accepted by `output_contract.schema`.
OUTPUT_SCHEMAS: frozenset[str] = frozenset((*STRUCTURED_KINDS, "markdown"))

ModelProfile = Literal["strong", "balanced", "fast"]
LangCode = Annotated[str, StringConstraints(pattern=r"^[a-z]{2}(-[A-Z]{2})?$")]


class Prompts(StrictModel):
    system: RelPath = Field(description="Required; at most 12 000 characters.")
    examples: RelPath | None = None


class OutputContract(StrictModel):
    artifacts: Annotated[list[str], Field(min_length=1)]
    output_schema: str = Field(alias="schema")

    @model_validator(mode="after")
    def _check_kinds(self) -> "OutputContract":
        unknown = sorted(set(self.artifacts) - ARTIFACT_KINDS)
        if unknown:
            raise ValueError(f"unknown artifact kind(s): {', '.join(unknown)}")
        if self.output_schema not in OUTPUT_SCHEMAS:
            raise ValueError(
                f"schema must be one of {', '.join(sorted(OUTPUT_SCHEMAS))}, "
                f"got {self.output_schema!r}"
            )
        if self.output_schema != "markdown" and self.output_schema not in self.artifacts:
            raise ValueError(f"schema {self.output_schema!r} must be listed in artifacts")
        return self


class Limits(StrictModel):
    max_tool_calls: Annotated[int, Field(ge=1, le=50)] = 40
    max_output_tokens: Annotated[int, Field(ge=1)] = 8000
    turn_timeout_s: Annotated[int, Field(ge=1, le=900)] = 600


class Office(StrictModel):
    room: Ident | None = None
    avatar: RelPath | None = Field(default=None, description="glTF binary, at most 2 MB.")
    color: Annotated[str, StringConstraints(pattern=r"^#[0-9a-fA-F]{6}$")] | None = None


class Capabilities(StrictModel):
    may_ask: bool = False
    reads_untrusted: bool = False


class I18n(StrictModel):
    display_name: dict[LangCode, str] = Field(default_factory=dict)


class Agent(ExtensibleModel):
    """Agent definition (`kind: agent`)."""

    schema_version: SchemaVersion = Field(alias="schema")
    role: Ident
    display_name: Annotated[str, StringConstraints(min_length=1)]
    model_profile: ModelProfile
    tools: list[PermissionId] = Field(default_factory=list)
    requires_tools: list[PackageName] = Field(
        default_factory=list,
        description="Tool packages that expose permissions not in the core catalog.",
    )
    skills: list[PackageName] = Field(
        default_factory=list, description="Folder names under skills/."
    )
    prompts: Prompts
    output_contract: OutputContract
    limits: Limits = Limits()
    office: Office = Office()
    capabilities: Capabilities = Capabilities()
    i18n: I18n = I18n()
    args_policy: dict[PermissionId, dict[str, dict[str, Any]]] = Field(
        default_factory=dict,
        description="Per-tool argument rules added to the tool package's own (CD-032): "
        "`{permission: {argument: {pattern|const|enum|maxLength|minimum|maximum: ...}}}`.",
    )

    @model_validator(mode="after")
    def _no_duplicates(self) -> "Agent":
        for field in ("tools", "skills", "requires_tools"):
            values: list[str] = getattr(self, field)
            dupes = sorted({v for v in values if values.count(v) > 1})
            if dupes:
                raise ValueError(f"duplicate {field}: {', '.join(dupes)}")
        return self

    @model_validator(mode="after")
    def _check_args_policy(self) -> "Agent":
        for permission, rules in self.args_policy.items():
            if permission not in self.tools:
                raise ValueError(f"args_policy for {permission!r}, which is not in tools")
            for argument, rule in rules.items():
                unknown = sorted(set(rule) - ARGS_POLICY_KEYWORDS)
                if unknown:
                    raise ValueError(
                        f"args_policy.{permission}.{argument}: unsupported keyword(s) "
                        f"{', '.join(unknown)}"
                    )
                if "pattern" in rule:
                    try:
                        re.compile(str(rule["pattern"]))
                    except re.error as exc:
                        raise ValueError(
                            f"args_policy.{permission}.{argument}: invalid pattern: {exc}"
                        ) from exc
        return self

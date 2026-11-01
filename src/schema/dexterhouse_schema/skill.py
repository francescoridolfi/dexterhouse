# SPDX-License-Identifier: AGPL-3.0-or-later
"""`skills/<name>/SKILL.md`: Agent Skills frontmatter (CD-014) and Markdown body."""

from dataclasses import dataclass
from typing import Annotated, Any, Literal

import yaml
from pydantic import ConfigDict, Field, StringConstraints

from dexterhouse_schema.common import (
    Ident,
    PackageName,
    PermissionId,
    SchemaVersion,
    StrictModel,
)

MAX_SKILL_BODY_CHARS = 30_000


class DexterhouseSkillMeta(StrictModel):
    """The strict `dexterhouse:` block of the frontmatter."""

    schema_version: SchemaVersion = Field(alias="schema")
    tools_required: list[PermissionId] = Field(
        default_factory=list, description="The skill is listed only if the agent has all of them."
    )
    cost_hint: Literal["low", "medium", "high"] = "medium"
    rooms: list[Ident] = Field(default_factory=list)


class SkillFrontmatter(StrictModel):
    """Frontmatter of a SKILL.md. Unknown top-level keys are kept (other runtimes)."""

    model_config = ConfigDict(extra="allow")

    name: PackageName
    description: Annotated[str, StringConstraints(min_length=1, max_length=1024)]
    dexterhouse: DexterhouseSkillMeta | None = None


@dataclass(frozen=True)
class SkillDocument:
    """A SKILL.md split into its raw frontmatter mapping and Markdown body."""

    frontmatter: dict[str, Any]
    body: str


def split_skill_md(text: str) -> SkillDocument:
    """Split a SKILL.md into frontmatter and body.

    Raises:
        ValueError: missing or unterminated frontmatter, or frontmatter not a mapping.
    """
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        raise ValueError("SKILL.md must start with a '---' frontmatter block")
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            try:
                data = yaml.safe_load("".join(lines[1:index]))
            except yaml.YAMLError as exc:
                raise ValueError(f"invalid YAML frontmatter: {exc}") from exc
            if not isinstance(data, dict):
                raise ValueError("frontmatter must be a mapping")
            return SkillDocument(frontmatter=data, body="".join(lines[index + 1 :]))
    raise ValueError("unterminated frontmatter block")

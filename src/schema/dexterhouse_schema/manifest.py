# SPDX-License-Identifier: AGPL-3.0-or-later
"""`dexterhouse.yaml`: the manifest at the root of every package."""

from typing import Annotated, Literal

from pydantic import Field, StringConstraints

from dexterhouse_schema.common import (
    ExtensibleModel,
    GithubUser,
    HttpUrl,
    PackageName,
    RelPath,
    SchemaVersion,
    SemVer,
    StrictModel,
    VersionRange,
)

PackageKind = Literal["agent", "tool", "process"]

#: Definition file expected next to the manifest for each kind.
DEFINITION_FILES: dict[str, str] = {
    "agent": "agent.yaml",
    "tool": "tool.yaml",
    "process": "process.yaml",
}

# SPDX license expression: ids joined by AND/OR/WITH, optional parentheses.
_SPDX = r"^[A-Za-z0-9.+()-]+( (AND|OR|WITH) [A-Za-z0-9.+()-]+)*$"
Tag = Annotated[str, StringConstraints(pattern=r"^[a-z0-9-]+$")]


class Author(StrictModel):
    name: Annotated[str, StringConstraints(min_length=1)]
    github: GithubUser | None = Field(
        default=None, description="Required to publish in the registry."
    )
    url: HttpUrl | None = None


class Compat(StrictModel):
    core: VersionRange = Field(description="PEP 440 range of supported core versions.")


class Manifest(ExtensibleModel):
    """Package manifest. `version` is semver 2.0, `compat.core` a PEP 440 range."""

    schema_version: SchemaVersion = Field(alias="schema")
    kind: PackageKind
    name: PackageName
    version: SemVer
    description: Annotated[str, StringConstraints(max_length=200)]
    author: Author
    license: Annotated[str, StringConstraints(pattern=_SPDX)]
    compat: Compat
    tags: Annotated[list[Tag], Field(max_length=10)] = Field(default_factory=list)
    homepage: HttpUrl | None = None
    readme: RelPath = "README.md"
    icon: RelPath | None = Field(default=None, description="At most 256 KB.")

    @property
    def definition_file(self) -> str:
        """Name of the definition file matching :attr:`kind`."""
        return DEFINITION_FILES[self.kind]

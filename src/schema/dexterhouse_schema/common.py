# SPDX-License-Identifier: AGPL-3.0-or-later
"""Shared base models, constrained types and constants used by every schema."""

import re
from typing import Annotated, Any, ClassVar
from urllib.parse import urlparse

from packaging.specifiers import InvalidSpecifier, SpecifierSet
from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    ModelWrapValidatorHandler,
    PrivateAttr,
    StringConstraints,
    WithJsonSchema,
    model_validator,
)
from pydantic_core import PydanticCustomError

from dexterhouse_schema.semver import SEMVER_PATTERN

#: Values of `schema:` this release understands (CD-019: the core keeps the last two).
SUPPORTED_SCHEMAS: frozenset[int] = frozenset({1})

PACKAGE_NAME_PATTERN = r"^[a-z][a-z0-9-]{2,63}$"
IDENT_PATTERN = r"^[a-z][a-z0-9_]{2,63}$"
PERMISSION_ID_PATTERN = r"^[a-z][a-z0-9]*\.[a-z][a-z0-9_]*$"
GITHUB_PATTERN = r"^[A-Za-z0-9-]{1,39}$"
TASK_ID_PATTERN = r"^T-\d{2,3}$"

#: Structured artifact kinds: `data` validated by a schema in `dexterhouse_schema.artifacts`.
STRUCTURED_KINDS: tuple[str, ...] = (
    "stack",
    "task_board",
    "team_proposal",
    "questions",
    "assumptions",
    "review",
    "test_report",
    "code_graph",
)
#: Text artifact kinds: Markdown `content` following `agents/artifact_templates.md`.
TEXT_KINDS: tuple[str, ...] = (
    "brief",
    "requirements",
    "user_stories",
    "architecture",
    "adr",
    "dev_notes",
    "release_notes",
    "retrospective",
    "file",
)
ARTIFACT_KINDS: frozenset[str] = frozenset(STRUCTURED_KINDS + TEXT_KINDS)


def _check_schema_version(value: int) -> int:
    if value not in SUPPORTED_SCHEMAS:
        raise PydanticCustomError(
            "unsupported_schema",
            "unsupported schema version {value}; supported: {supported}",
            {"value": value, "supported": ", ".join(map(str, sorted(SUPPORTED_SCHEMAS)))},
        )
    return value


#: `schema: N` field. Errors use the type `unsupported_schema` so the core can mark the
#: package `incompatible` instead of invalid.
SchemaVersion = Annotated[
    int,
    AfterValidator(_check_schema_version),
    WithJsonSchema({"type": "integer", "enum": sorted(SUPPORTED_SCHEMAS)}),
]

PackageName = Annotated[str, StringConstraints(pattern=PACKAGE_NAME_PATTERN)]
Ident = Annotated[str, StringConstraints(pattern=IDENT_PATTERN)]
PermissionId = Annotated[str, StringConstraints(pattern=PERMISSION_ID_PATTERN)]
GithubUser = Annotated[str, StringConstraints(pattern=GITHUB_PATTERN)]
SemVer = Annotated[str, StringConstraints(pattern=SEMVER_PATTERN)]
NonEmptyStr = Annotated[str, StringConstraints(min_length=1, pattern=r"\S")]
TaskId = Annotated[str, StringConstraints(pattern=TASK_ID_PATTERN)]


def _check_specifier(value: str) -> str:
    try:
        SpecifierSet(value)
    except InvalidSpecifier as exc:
        raise ValueError(f"invalid PEP 440 version range: {value!r}") from exc
    if not value.strip():
        raise ValueError("version range must not be empty")
    return value


#: PEP 440 range such as `>=1.0,<2.0`.
VersionRange = Annotated[str, AfterValidator(_check_specifier)]


def _check_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"not an http(s) URL: {value!r}")
    return value


HttpUrl = Annotated[str, AfterValidator(_check_url), Field(json_schema_extra={"format": "uri"})]

_REL_PATH_RE = re.compile(r"^[^/\\\x00]")


def check_relative_path(value: str) -> str:
    """Reject absolute paths, backslashes and `..` segments (existence is checked later)."""
    if not value or not _REL_PATH_RE.match(value) or "\\" in value or ":" in value[:2]:
        raise ValueError(f"path must be relative to the package root: {value!r}")
    if ".." in value.split("/"):
        raise ValueError(f"path must not contain '..': {value!r}")
    return value


RelPath = Annotated[str, AfterValidator(check_relative_path)]


class StrictModel(BaseModel):
    """Base for every schema: unknown fields are rejected and types are not coerced."""

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        validate_by_alias=True,
        validate_by_name=True,
        serialize_by_alias=True,
    )


class ExtensibleModel(StrictModel):
    """Root model of a package file: unknown keys are rejected unless prefixed by `x-`.

    The `x-` keys are removed before validation and kept in :attr:`extensions`.
    """

    model_config = ConfigDict(
        json_schema_extra={"patternProperties": {"^x-": {}}},
    )
    _extensions: dict[str, Any] = PrivateAttr(default_factory=dict)
    EXTENSION_PREFIX: ClassVar[str] = "x-"

    @model_validator(mode="wrap")
    @classmethod
    def _split_extensions(cls, data: Any, handler: ModelWrapValidatorHandler[Any]) -> Any:
        ext: dict[str, Any] = {}
        if isinstance(data, dict):
            ext = {k: v for k, v in data.items() if str(k).startswith(cls.EXTENSION_PREFIX)}
            data = {k: v for k, v in data.items() if k not in ext}
        model = handler(data)
        if ext:
            model._extensions = ext
        return model

    @property
    def extensions(self) -> dict[str, Any]:
        """The `x-` keys found at the root of the file."""
        return dict(self._extensions)

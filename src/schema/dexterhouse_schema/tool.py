# SPDX-License-Identifier: AGPL-3.0-or-later
"""`tool.yaml`: descriptor of an MCP server exposed as a tool package."""

import re
from typing import Annotated, Any, Literal

from packaging.version import InvalidVersion, Version
from pydantic import Field, StringConstraints, model_validator

from dexterhouse_schema.common import (
    ExtensibleModel,
    HttpUrl,
    PackageName,
    PermissionId,
    SchemaVersion,
    StrictModel,
    check_relative_path,
)
from dexterhouse_schema.semver import SEMVER_PATTERN

Risk = Literal["low", "medium", "high"]
RISK_ORDER: dict[str, int] = {"low": 0, "medium": 1, "high": 2}

#: Launchers accepted as `command[0]`, besides a relative path to a file in the package.
LAUNCHERS: frozenset[str] = frozenset({"uvx", "npx", "python", "node"})

_INTERPOLATION_RE = re.compile(r"\$\{([^}]*)\}")
_ALLOWED_INTERPOLATION_RE = re.compile(r"^(workspace\.path|project\.[a-z][a-z0-9_]*)$")
_LABEL = r"[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?"
_HOST_PATTERN = rf"^{_LABEL}(\.{_LABEL})*$"
_SEMVER_RE = re.compile(SEMVER_PATTERN)
_NPX_FLAGS = frozenset({"-y", "--yes", "-q", "--quiet"})

EnvName = Annotated[str, StringConstraints(pattern=r"^[A-Z_][A-Z0-9_]*$")]
Host = Annotated[str, StringConstraints(pattern=_HOST_PATTERN, max_length=253)]


def check_interpolations(value: Any, where: str) -> None:
    """Only `${workspace.path}` and `${project.*}` may be interpolated (recursive)."""
    if isinstance(value, str):
        for expr in _INTERPOLATION_RE.findall(value):
            if not _ALLOWED_INTERPOLATION_RE.match(expr):
                raise ValueError(f"{where}: interpolation ${{{expr}}} is not allowed")
    elif isinstance(value, dict):
        for key, item in value.items():
            check_interpolations(item, f"{where}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            check_interpolations(item, f"{where}[{index}]")


def _is_pinned_pypi(spec: str) -> bool:
    name, sep, version = spec.partition("==") if "==" in spec else spec.partition("@")
    if not sep or not name:
        return False
    try:
        Version(version)
    except InvalidVersion:
        return False
    return True


def _is_pinned_npm(spec: str) -> bool:
    at = spec.rfind("@")
    return at > 0 and bool(_SEMVER_RE.match(spec[at + 1 :]))


def check_command(command: list[str]) -> None:
    """`command[0]` is an allowed launcher and the launched package is pinned."""
    launcher, args = command[0], command[1:]
    if launcher not in LAUNCHERS:
        if "/" not in launcher:
            raise ValueError(
                f"command[0] {launcher!r} must be one of {', '.join(sorted(LAUNCHERS))} "
                "or a relative path to a file inside the package"
            )
        check_relative_path(launcher)
        return
    if launcher == "uvx":
        spec = args[args.index("--from") + 1] if "--from" in args[:-1] else _first_positional(args)
        if spec is None or not _is_pinned_pypi(spec):
            raise ValueError(f"uvx package must be pinned (pkg@X.Y.Z or pkg==X.Y.Z): {spec!r}")
    elif launcher == "npx":
        spec = _first_positional([a for a in args if a not in _NPX_FLAGS])
        if spec is None or not _is_pinned_npm(spec):
            raise ValueError(f"npx package must be pinned to an exact version: {spec!r}")


def _first_positional(args: list[str]) -> str | None:
    return next((a for a in args if not a.startswith("-")), None)


class Permission(StrictModel):
    id: PermissionId = Field(description="`<name prefix>.<verb>`.")
    mcp_tool: Annotated[str, StringConstraints(min_length=1)]
    description: str | None = None
    risk: Risk
    args_policy: dict[str, dict[str, Any]] | None = Field(
        default=None, description="JSON Schema subset applied to each argument."
    )


class Healthcheck(StrictModel):
    timeout_s: Annotated[int, Field(gt=0)] = 10


class Tool(ExtensibleModel):
    """Tool definition (`kind: tool`).

    The permission prefix is the part of `name` before the first `-`
    (`git-tools` exposes `git.*`).
    """

    schema_version: SchemaVersion = Field(alias="schema")
    name: PackageName
    transport: Literal["stdio", "http"]
    runs_in: Literal["runner", "worker"]
    command: Annotated[list[str], Field(min_length=1)] | None = None
    url: HttpUrl | None = None
    env: dict[EnvName, str] = Field(default_factory=dict)
    permissions: Annotated[list[Permission], Field(min_length=1)]
    network: Literal["none", "allowlist"] = "none"
    hosts: list[Host] = Field(default_factory=list)
    healthcheck: Healthcheck = Healthcheck()

    @property
    def permission_prefix(self) -> str:
        return self.name.split("-", 1)[0]

    @property
    def max_risk(self) -> Risk:
        """Highest risk among the permissions (the registry index `risk`)."""
        return max((p.risk for p in self.permissions), key=RISK_ORDER.__getitem__)

    @model_validator(mode="after")
    def _check(self) -> "Tool":
        self._check_placement()
        if self.transport == "stdio":
            if self.command is None or self.url is not None:
                raise ValueError("transport stdio requires `command` and no `url`")
            check_command(self.command)
        elif self.url is None or self.command is not None:
            raise ValueError("transport http requires `url` and no `command`")
        ids = [p.id for p in self.permissions]
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        if dupes:
            raise ValueError(f"duplicate permission id(s): {', '.join(dupes)}")
        for perm in self.permissions:
            if perm.id.split(".", 1)[0] != self.permission_prefix:
                raise ValueError(
                    f"permission {perm.id!r} must start with {self.permission_prefix + '.'!r}"
                )
            check_interpolations(perm.args_policy, f"permissions.{perm.id}.args_policy")
        check_interpolations(self.env, "env")
        return self

    def _check_placement(self) -> None:
        if self.runs_in == "runner":
            if self.transport != "stdio" or self.network != "none":
                raise ValueError("runs_in runner requires transport stdio and network none")
        elif self.network != "allowlist" or not self.hosts:
            raise ValueError("runs_in worker requires network allowlist with explicit hosts")
        if self.network == "none" and self.hosts:
            raise ValueError("hosts must be empty when network is none")

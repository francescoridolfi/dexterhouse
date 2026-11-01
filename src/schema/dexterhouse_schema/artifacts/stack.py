# SPDX-License-Identifier: AGPL-3.0-or-later
"""`stack`: machine-readable stack chosen by the architect."""

import re
from typing import Annotated, Literal

from pydantic import AfterValidator, Field, StringConstraints

from dexterhouse_schema.common import StrictModel

MAX_COMMAND_CHARS = 300
MAX_AND_CHAINS = 3
_SUDO_RE = re.compile(r"(^|[\s;&|(`])sudo(\s|$)")


def check_command(value: str) -> str:
    """At most 300 chars, at most 3 `&&`, no `sudo`."""
    if len(value) > MAX_COMMAND_CHARS:
        raise ValueError(f"command longer than {MAX_COMMAND_CHARS} characters")
    if value.count("&&") > MAX_AND_CHAINS:
        raise ValueError(f"command chains more than {MAX_AND_CHAINS} '&&'")
    if _SUDO_RE.search(value):
        raise ValueError("command must not use sudo")
    return value


Command = Annotated[str, StringConstraints(min_length=1), AfterValidator(check_command)]
Port = Annotated[int, Field(ge=1024, le=65535)]


class Stack(StrictModel):
    language: Literal["python", "node", "go", "rust", "java", "other"]
    framework: str
    workspace_image: Literal[
        "dexterhouse/workspace:python", "dexterhouse/workspace:node", "dexterhouse/workspace:full"
    ]
    package_manager: Literal["uv", "pip", "npm", "pnpm", "yarn", "go", "cargo", "maven"]
    test_command: Command
    run_command: Command
    lint_command: Command | None = None
    install_command: Command | None = None
    services: list[Literal["postgres", "redis", "mailpit"]] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    ports: list[Port] = Field(default_factory=list)
    healthcheck_path: Annotated[str, StringConstraints(pattern=r"^/")] | None = None
    notes: str | None = None

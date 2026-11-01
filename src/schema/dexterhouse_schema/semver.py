# SPDX-License-Identifier: AGPL-3.0-or-later
"""Minimal Semantic Versioning 2.0 parsing and precedence (no build metadata)."""

import re
from functools import total_ordering

_NUM = r"0|[1-9]\d*"
_PRE_ID = r"0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*"
SEMVER_PATTERN = rf"^({_NUM})\.({_NUM})\.({_NUM})(?:-((?:{_PRE_ID})(?:\.(?:{_PRE_ID}))*))?$"
_SEMVER_RE = re.compile(SEMVER_PATTERN)


@total_ordering
class SemanticVersion:
    """A parsed semver value ordered by semver precedence rules."""

    def __init__(self, text: str) -> None:
        match = _SEMVER_RE.match(text)
        if match is None:
            raise ValueError(f"not a semantic version: {text!r}")
        self.text = text
        self.core = (int(match[1]), int(match[2]), int(match[3]))
        self.pre: tuple[str, ...] = tuple(match[4].split(".")) if match[4] else ()

    def _key(self) -> tuple[tuple[int, int, int], int, tuple[tuple[int, int, str], ...]]:
        # A release sorts after any pre-release of the same core version.
        pre = tuple((0, int(p), "") if p.isdigit() else (1, 0, p) for p in self.pre)
        return (self.core, 0 if self.pre else 1, pre)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, SemanticVersion) and self._key() == other._key()

    def __lt__(self, other: "SemanticVersion") -> bool:
        return self._key() < other._key()

    def __hash__(self) -> int:
        return hash(self._key())

    def __repr__(self) -> str:
        return f"SemanticVersion({self.text!r})"

# SPDX-License-Identifier: AGPL-3.0-or-later
"""Structured validation results (path + message) instead of exceptions."""

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ValidationError


@dataclass(frozen=True)
class Issue:
    """One problem found in a file. `loc` is the dotted location inside the file, if any."""

    path: str
    message: str
    loc: str = ""

    def __str__(self) -> str:
        where = f"{self.path}: {self.loc}" if self.loc else self.path
        return f"{where}: {self.message}"


@dataclass
class ValidationReport:
    """Errors make the package invalid; warnings are requirements or advice."""

    errors: list[Issue] = field(default_factory=list)
    warnings: list[Issue] = field(default_factory=list)
    models: dict[str, BaseModel] = field(default_factory=dict)
    """Validated models by relative path (e.g. `dexterhouse.yaml`, `skills/x/SKILL.md`)."""

    @property
    def ok(self) -> bool:
        return not self.errors

    def error(self, path: str, message: str, loc: str = "") -> None:
        self.errors.append(Issue(path, message, loc))

    def warn(self, path: str, message: str, loc: str = "") -> None:
        self.warnings.append(Issue(path, message, loc))

    def add_validation_error(self, path: str, exc: ValidationError) -> None:
        for err in exc.errors(include_url=False):
            self.error(path, _clean_message(err), _format_loc(err["loc"]))


def _format_loc(loc: tuple[Any, ...]) -> str:
    parts: list[str] = []
    for item in loc:
        if isinstance(item, int):
            parts.append(f"[{item}]")
        else:
            parts.append(f".{item}" if parts else str(item))
    return "".join(parts)


def _clean_message(err: Any) -> str:
    message = str(err["msg"])
    return message.removeprefix("Value error, ")


def validation_messages(exc: ValidationError) -> list[str]:
    """Flatten a pydantic error into `loc: message` lines (useful for reprompts)."""
    report = ValidationReport()
    report.add_validation_error("", exc)
    return [f"{i.loc}: {i.message}" if i.loc else i.message for i in report.errors]

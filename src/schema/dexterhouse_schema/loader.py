# SPDX-License-Identifier: AGPL-3.0-or-later
"""Read YAML/JSON files and validate them into models, recording issues in a report."""

import json
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ValidationError

from dexterhouse_schema.report import ValidationReport


def read_text(path: Path, rel: str, report: ValidationReport) -> str | None:
    """UTF-8 text of `path`, or None after recording why it cannot be read."""
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        report.error(rel, "file is not valid UTF-8")
    except OSError as exc:
        report.error(rel, f"cannot read file: {exc.strerror or exc}")
    return None


#: Returned by :func:`load_data` when the file could not be read or parsed.
UNREADABLE: Any = object()


def load_data(path: Path, rel: str, report: ValidationReport) -> Any:
    """Parse a YAML (or JSON, by suffix) file; :data:`UNREADABLE` after recording an error."""
    text = read_text(path, rel, report)
    if text is None:
        return UNREADABLE
    try:
        if path.suffix == ".json":
            return json.loads(text)
        return yaml.safe_load(text)
    except (yaml.YAMLError, json.JSONDecodeError) as exc:
        report.error(rel, f"cannot parse file: {exc}")
    return UNREADABLE


def load_model[M: BaseModel](
    path: Path, rel: str, model: type[M], report: ValidationReport
) -> M | None:
    """Load `path` and validate it as `model`; the result is stored in `report.models`."""
    data = load_data(path, rel, report)
    if data is UNREADABLE:
        return None
    if not isinstance(data, dict):
        report.error(rel, "top level must be a mapping")
        return None
    try:
        instance = model.model_validate(data)
    except ValidationError as exc:
        report.add_validation_error(rel, exc)
        return None
    report.models[rel] = instance
    return instance

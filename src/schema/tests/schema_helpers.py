# SPDX-License-Identifier: AGPL-3.0-or-later
"""Helpers shared by the dexterhouse-schema tests."""

import copy
import json
import shutil
from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import BaseModel, ValidationError

FIXTURES = Path(__file__).parent / "fixtures"
PACKAGES = FIXTURES / "packages"
DELETE = object()


def load_yaml(relpath: str) -> dict[str, Any]:
    return yaml.safe_load((FIXTURES / relpath).read_text(encoding="utf-8"))


def load_json(relpath: str) -> Any:
    return json.loads((FIXTURES / relpath).read_text(encoding="utf-8"))


def patched(data: Any, changes: dict[str, Any]) -> Any:
    """Deep copy of `data` with dotted-path changes (`a.b.0.c`); DELETE removes a key."""
    result = copy.deepcopy(data)
    for dotted, value in changes.items():
        *parents, last = dotted.split(".")
        node = result
        for part in parents:
            node = node[int(part)] if isinstance(node, list) else node[part]
        key: Any = int(last) if isinstance(node, list) else last
        if value is DELETE:
            del node[key]
        else:
            node[key] = value
    return result


def assert_invalid(
    model: type[BaseModel], data: Any, match: str, context: Any = None
) -> ValidationError:
    with pytest.raises(ValidationError, match=match) as info:
        model.model_validate(data, context=context)
    return info.value


def copy_package(name: str, tmp_path: Path) -> Path:
    target = tmp_path / name
    shutil.copytree(PACKAGES / name, target)
    return target

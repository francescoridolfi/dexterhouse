# SPDX-License-Identifier: AGPL-3.0-or-later
"""A test marketplace: index entries plus package files served from a `file://` raw tree."""

import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from dexterhouse.apps.packages.services import shared_cache

from .conftest import index_entry, sha_of, write_package

OWNER = "https://github.com/dh-test"


def agent_definition(role: str, tools: list[str], room: str = "dev_room") -> dict[str, Any]:
    return {
        "schema": 1,
        "role": role,
        "display_name": role.replace("_", " ").title(),
        "model_profile": "balanced",
        "tools": tools,
        "skills": [],
        "prompts": {"system": "prompts/system.md"},
        "output_contract": {"artifacts": ["dev_notes"], "schema": "markdown"},
        "office": {"room": room},
    }


@pytest.fixture(autouse=True)
def _clean_marketplace_cache():
    shared_cache.clear()
    yield
    shared_cache.clear()


@pytest.fixture
def raw_tree(settings, tmp_path: Path) -> Path:
    """`MARKETPLACE_RAW_URL` pointing at `tmp_path/raw/{path}/{ref}/{file}`."""
    root = tmp_path / "raw"
    root.mkdir()
    settings.MARKETPLACE_RAW_URL = f"{root.as_uri()}/{{path}}/{{ref}}/{{file}}"
    return root


@pytest.fixture
def publish(tmp_path: Path, raw_tree: Path, index_file) -> Callable[..., dict[str, Any]]:
    """Write packages, their raw files and the index; returns {name: entry}."""
    entries: dict[str, dict[str, Any]] = {}

    def add(
        name: str,
        *,
        kind: str = "agent",
        version: str = "1.0.0",
        definition: dict[str, Any] | None = None,
        readme: str | None = None,
        **extra: Any,
    ) -> dict[str, Any]:
        src = write_package(tmp_path / "pkgs" / name, name, kind, version, definition=definition)
        if readme is not None:
            (src / "README.md").write_text(readme)
        ref = f"v{version}"
        shutil.copytree(src, raw_tree / "dh-test" / name / ref, dirs_exist_ok=True)
        entries[name] = index_entry(
            name, f"{OWNER}/{name}", [(version, ref, sha_of(src))], kind=kind, **extra
        )
        index_file(*entries.values())
        return entries[name]

    return add

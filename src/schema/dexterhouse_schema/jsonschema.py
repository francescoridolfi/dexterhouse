# SPDX-License-Identifier: AGPL-3.0-or-later
"""JSON Schema (draft 2020-12) export of every top-level schema.

Cross-field rules implemented as validators (graph checks, verdict rules, ...) cannot be
expressed in JSON Schema: the pydantic models remain the reference.
"""

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from dexterhouse_schema.agent import Agent
from dexterhouse_schema.artifacts import ARTIFACT_MODELS
from dexterhouse_schema.common import SUPPORTED_SCHEMAS
from dexterhouse_schema.manifest import Manifest
from dexterhouse_schema.process import Process
from dexterhouse_schema.registry import RegistryIndex, RegistryPackage
from dexterhouse_schema.skill import SkillFrontmatter
from dexterhouse_schema.tool import Tool
from dexterhouse_schema.turn_output import TurnOutput

DRAFT = "https://json-schema.org/draft/2020-12/schema"
BASE_ID = "https://dexterhouse.dev/schema/{version}/{name}.json"

TOP_LEVEL_SCHEMAS: dict[str, type[BaseModel]] = {
    "manifest": Manifest,
    "agent": Agent,
    "tool": Tool,
    "process": Process,
    "skill": SkillFrontmatter,
    "registry_package": RegistryPackage,
    "registry_index": RegistryIndex,
    "turn_output": TurnOutput,
    **{f"artifact_{kind}": model for kind, model in ARTIFACT_MODELS.items()},
}


def json_schema(name: str) -> dict[str, Any]:
    """JSON Schema of the top-level schema `name` (a key of :data:`TOP_LEVEL_SCHEMAS`)."""
    schema = TOP_LEVEL_SCHEMAS[name].model_json_schema(by_alias=True, mode="validation")
    version = max(SUPPORTED_SCHEMAS)
    return {"$schema": DRAFT, "$id": BASE_ID.format(version=version, name=name), **schema}


def export_json_schemas(out_dir: str | Path) -> list[Path]:
    """Write `<name>.json` for every top-level schema into `out_dir`; return the paths."""
    target = Path(out_dir)
    target.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name in TOP_LEVEL_SCHEMAS:
        path = target / f"{name}.json"
        path.write_text(json.dumps(json_schema(name), indent=2) + "\n", encoding="utf-8")
        written.append(path)
    return written

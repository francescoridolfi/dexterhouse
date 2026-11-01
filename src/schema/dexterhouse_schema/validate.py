# SPDX-License-Identifier: AGPL-3.0-or-later
"""Single entry point: validate a package directory or one known file."""

from pathlib import Path

from dexterhouse_schema.agent import Agent
from dexterhouse_schema.loader import load_model
from dexterhouse_schema.manifest import Manifest
from dexterhouse_schema.package import MANIFEST_FILE, validate_package
from dexterhouse_schema.process import Process
from dexterhouse_schema.registry import RegistryIndex, RegistryPackage
from dexterhouse_schema.report import ValidationReport
from dexterhouse_schema.skill_check import validate_skill_dir
from dexterhouse_schema.tool import Tool

_YAML_MODELS = {
    MANIFEST_FILE: Manifest,
    "agent.yaml": Agent,
    "tool.yaml": Tool,
    "process.yaml": Process,
}


def validate_registry_package_file(path: Path) -> ValidationReport:
    """Validate `packages/<name>.json`, including `<name>` equal to the `name` field."""
    report = ValidationReport()
    package = load_model(path, path.name, RegistryPackage, report)
    if package and package.name != path.stem:
        report.error(path.name, f"file name must be {package.name}.json", "name")
    return report


def validate_path(path: str | Path) -> ValidationReport:
    """Validate a package directory, or a single file recognized by its name.

    Files: `dexterhouse.yaml`, `agent.yaml`, `tool.yaml`, `process.yaml` (schema only,
    references are not resolved), `SKILL.md` (its folder), `index.json` and any other
    `.json` as a registry `packages/<name>.json`.
    """
    target = Path(path)
    if target.is_dir():
        return validate_package(target)
    report = ValidationReport()
    if not target.is_file():
        report.error(str(target), "no such file or directory")
    elif target.name in _YAML_MODELS:
        load_model(target, target.name, _YAML_MODELS[target.name], report)
    elif target.name == "SKILL.md":
        validate_skill_dir(target.parent, target.parent.name, report)
    elif target.name == "index.json":
        load_model(target, target.name, RegistryIndex, report)
    elif target.suffix == ".json":
        return validate_registry_package_file(target)
    else:
        report.error(str(target), "unsupported file: expected a package directory or a known file")
    return report

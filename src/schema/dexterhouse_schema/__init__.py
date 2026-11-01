# SPDX-License-Identifier: AGPL-3.0-or-later
"""Schemas and validator for DexterHouse packages.

Main entry points:

- :func:`validate_package` / :func:`validate_path`: a package directory (or one file)
  into a :class:`ValidationReport` of errors and warnings.
- :func:`validate_turn_output`: a TurnOutput, optionally with a :class:`TurnContext`.
- :func:`validate_artifact`: the `data` of a structured artifact kind.
- :func:`export_json_schemas`: JSON Schema draft 2020-12 files.
"""

from dexterhouse_schema.agent import Agent
from dexterhouse_schema.artifacts import ARTIFACT_MODELS, validate_artifact
from dexterhouse_schema.common import ARTIFACT_KINDS, STRUCTURED_KINDS, SUPPORTED_SCHEMAS
from dexterhouse_schema.context import TurnContext
from dexterhouse_schema.jsonschema import export_json_schemas, json_schema
from dexterhouse_schema.manifest import Manifest
from dexterhouse_schema.package import validate_package
from dexterhouse_schema.process import Process
from dexterhouse_schema.registry import RegistryIndex, RegistryPackage, check_registry_update
from dexterhouse_schema.report import Issue, ValidationReport, validation_messages
from dexterhouse_schema.skill import SkillFrontmatter
from dexterhouse_schema.tool import Tool
from dexterhouse_schema.turn_output import TurnOutput, extract_turn_json, validate_turn_output
from dexterhouse_schema.validate import validate_path, validate_registry_package_file

__version__ = "0.1.0"

__all__ = [
    "ARTIFACT_KINDS",
    "ARTIFACT_MODELS",
    "STRUCTURED_KINDS",
    "SUPPORTED_SCHEMAS",
    "Agent",
    "Issue",
    "Manifest",
    "Process",
    "RegistryIndex",
    "RegistryPackage",
    "SkillFrontmatter",
    "Tool",
    "TurnContext",
    "TurnOutput",
    "ValidationReport",
    "__version__",
    "check_registry_update",
    "export_json_schemas",
    "extract_turn_json",
    "json_schema",
    "validate_artifact",
    "validate_package",
    "validate_path",
    "validate_registry_package_file",
    "validate_turn_output",
    "validation_messages",
]

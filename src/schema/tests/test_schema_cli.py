# SPDX-License-Identifier: AGPL-3.0-or-later
import json
from pathlib import Path

import pytest
from schema_helpers import PACKAGES, copy_package

from dexterhouse_schema import TurnOutput, json_schema
from dexterhouse_schema.cli import main
from dexterhouse_schema.jsonschema import DRAFT, TOP_LEVEL_SCHEMAS


def test_validate_valid_package(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["validate", str(PACKAGES / "security-reviewer")]) == 0
    out, err = capsys.readouterr()
    assert out.endswith("security-reviewer: valid\n")
    assert err == ""


def test_validate_prints_warnings(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["validate", str(PACKAGES / "code-review-only")]) == 0
    assert "warning: process.yaml: process requires `stack`" in capsys.readouterr().err


def test_validate_invalid_package(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    pkg = copy_package("git-tools", tmp_path)
    (pkg / "README.md").unlink()
    assert main(["validate", str(pkg)]) == 1
    out, err = capsys.readouterr()
    assert out == ""
    assert "error: dexterhouse.yaml: readme: referenced file 'README.md' does not exist" in err
    assert "invalid (1 error(s))" in err


def test_usage_errors(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as info:
        main([])
    assert info.value.code == 2
    with pytest.raises(SystemExit) as info:
        main(["--version"])
    assert info.value.code == 0
    assert "dexterhouse-schema 0.1.0" in capsys.readouterr().out


def test_export_jsonschema(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["export-jsonschema", str(tmp_path / "out")]) == 0
    written = sorted(p.name for p in (tmp_path / "out").iterdir())
    assert written == sorted(f"{name}.json" for name in TOP_LEVEL_SCHEMAS)
    assert len(capsys.readouterr().out.splitlines()) == len(TOP_LEVEL_SCHEMAS)
    manifest = json.loads((tmp_path / "out/manifest.json").read_text())
    assert manifest["$schema"] == DRAFT
    assert manifest["$id"] == "https://dexterhouse.dev/schema/1/manifest.json"


def test_json_schema_contents() -> None:
    manifest = json_schema("manifest")
    assert manifest["additionalProperties"] is False
    assert manifest["patternProperties"] == {"^x-": {}}
    assert manifest["properties"]["schema"].items() >= {"type": "integer", "enum": [1]}.items()
    assert set(manifest["required"]) >= {"schema", "kind", "name", "version", "license", "compat"}
    assert manifest["properties"]["homepage"]["anyOf"][0]["format"] == "uri"
    skill = json_schema("skill")
    assert skill["additionalProperties"] is True
    assert json_schema("artifact_review")["$id"].endswith("/artifact_review.json")
    turn = json_schema("turn_output")
    assert "discriminator" in turn["properties"]["artifacts"]["items"]
    assert TurnOutput.model_json_schema()["additionalProperties"] is False

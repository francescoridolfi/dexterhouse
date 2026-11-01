# SPDX-License-Identifier: AGPL-3.0-or-later
import pytest
from schema_helpers import DELETE, assert_invalid, load_yaml, patched

from dexterhouse_schema import Manifest

MANIFEST = load_yaml("packages/security-reviewer/dexterhouse.yaml")


def test_doc_example_is_valid() -> None:
    manifest = Manifest.model_validate(MANIFEST)
    assert manifest.kind == "agent"
    assert manifest.definition_file == "agent.yaml"
    assert manifest.readme == "README.md"


def test_defaults() -> None:
    manifest = Manifest.model_validate(patched(MANIFEST, {"readme": DELETE, "tags": DELETE}))
    assert manifest.readme == "README.md"
    assert manifest.tags == []


@pytest.mark.parametrize(
    ("changes", "match"),
    [
        ({"kind": "skill"}, "kind"),
        ({"name": "Security"}, "pattern"),
        ({"name": "ab"}, "pattern"),
        ({"version": "1.2"}, "pattern"),
        ({"version": 1.2}, "string"),
        ({"description": "x" * 201}, "at most 200"),
        ({"author.github": "jane_doe"}, "pattern"),
        ({"author.url": "ftp://example.com"}, "http"),
        ({"author": {"github": "janedoe"}}, "name"),
        ({"license": "MIT; rm -rf"}, "pattern"),
        ({"compat.core": "between 1 and 2"}, "PEP 440"),
        ({"compat.core": " "}, "empty"),
        ({"tags": [f"t{i}" for i in range(11)]}, "at most 10"),
        ({"tags": ["Security"]}, "pattern"),
        ({"homepage": "example.com"}, "http"),
        ({"icon": "/abs/icon.png"}, "relative"),
        ({"readme": "../README.md"}, "'..'"),
        ({"compat": DELETE}, "compat"),
    ],
)
def test_invalid(changes: dict[str, object], match: str) -> None:
    assert_invalid(Manifest, patched(MANIFEST, changes), match)

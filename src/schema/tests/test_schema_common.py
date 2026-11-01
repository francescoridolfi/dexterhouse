# SPDX-License-Identifier: AGPL-3.0-or-later
import pytest
from pydantic import ValidationError
from schema_helpers import load_yaml, patched

from dexterhouse_schema import SUPPORTED_SCHEMAS, Manifest
from dexterhouse_schema.common import check_relative_path
from dexterhouse_schema.semver import SemanticVersion

MANIFEST = load_yaml("packages/security-reviewer/dexterhouse.yaml")


def test_supported_schemas() -> None:
    assert frozenset({1}) == SUPPORTED_SCHEMAS


@pytest.mark.parametrize("value", [0, 2, 99])
def test_unsupported_schema_has_dedicated_error_type(value: int) -> None:
    with pytest.raises(ValidationError) as info:
        Manifest.model_validate(patched(MANIFEST, {"schema": value}))
    (error,) = info.value.errors()
    assert error["type"] == "unsupported_schema"
    assert "supported: 1" in error["msg"]


@pytest.mark.parametrize("value", ["1", True, 1.0])
def test_schema_must_be_an_int(value: object) -> None:
    with pytest.raises(ValidationError):
        Manifest.model_validate(patched(MANIFEST, {"schema": value}))


def test_schema_field_is_serialized_by_alias() -> None:
    dumped = Manifest.model_validate(MANIFEST).model_dump()
    assert dumped["schema"] == 1
    assert "schema_version" not in dumped


def test_x_extensions_are_kept_and_other_unknown_keys_rejected() -> None:
    manifest = Manifest.model_validate(patched(MANIFEST, {"x-internal": {"team": "sec"}}))
    assert manifest.extensions == {"x-internal": {"team": "sec"}}
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        Manifest.model_validate(patched(MANIFEST, {"internal": 1}))


@pytest.mark.parametrize(
    ("lower", "higher"),
    [
        ("1.0.0", "1.0.1"),
        ("1.9.0", "1.10.0"),
        ("1.0.0-alpha", "1.0.0"),
        ("1.0.0-alpha", "1.0.0-alpha.1"),
        ("1.0.0-alpha.1", "1.0.0-alpha.beta"),
        ("1.0.0-beta.2", "1.0.0-beta.11"),
        ("1.0.0-rc.1", "1.0.0"),
    ],
)
def test_semver_precedence(lower: str, higher: str) -> None:
    assert SemanticVersion(lower) < SemanticVersion(higher)
    assert SemanticVersion(higher) > SemanticVersion(lower)


def test_semver_equality_and_errors() -> None:
    assert SemanticVersion("1.2.3") == SemanticVersion("1.2.3")
    assert SemanticVersion("1.2.3") != "1.2.3"
    assert len({SemanticVersion("1.2.3"), SemanticVersion("1.2.3")}) == 1
    assert "1.2.3" in repr(SemanticVersion("1.2.3"))
    for bad in ("1.2", "01.2.3", "1.2.3+build", "v1.2.3"):
        with pytest.raises(ValueError, match="not a semantic version"):
            SemanticVersion(bad)


@pytest.mark.parametrize("value", ["/etc/passwd", "../x", "a/../../b", "a\\b", "C:/x", ""])
def test_relative_path_rejections(value: str) -> None:
    with pytest.raises(ValueError, match="path must"):
        check_relative_path(value)


def test_relative_path_accepts_nested() -> None:
    assert check_relative_path("prompts/system.md") == "prompts/system.md"

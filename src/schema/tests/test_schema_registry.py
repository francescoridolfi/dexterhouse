# SPDX-License-Identifier: AGPL-3.0-or-later
from typing import Any

import pytest
from schema_helpers import assert_invalid, load_json, patched

from dexterhouse_schema import RegistryIndex, RegistryPackage, check_registry_update

PACKAGE = load_json("registry/packages/security-reviewer.json")
INDEX = load_json("registry/index.json")
SHA = "cd" * 32


def with_version(data: dict[str, Any], version: str, **extra: Any) -> dict[str, Any]:
    entry = {**data["versions"][0], "version": version, "ref": f"v{version}", "sha256": SHA}
    return {**data, "versions": [*data["versions"], {**entry, **extra}]}


def test_doc_examples_are_valid() -> None:
    package = RegistryPackage.model_validate(PACKAGE)
    assert package.versions[0].published_at.year == 2027
    index = RegistryIndex.model_validate(INDEX)
    assert index.packages[0].latest == "1.2.0"


@pytest.mark.parametrize(
    ("changes", "match"),
    [
        ({"versions.0.sha256": "…64 hex…"}, "pattern"),
        ({"versions.0.sha256": "AB" * 32}, "pattern"),
        ({"versions.0.compat_core": "1.x"}, "PEP 440"),
        ({"versions.0.published_at": "yesterday"}, "datetime"),
        ({"versions": []}, "at least 1"),
        ({"repo": "git@github.com:janedoe/x.git"}, "http"),
        ({"kind": "skill"}, "kind"),
        ({"replaced_by": "security-reviewer"}, "another package"),
        ({"verified": "false"}, "boolean"),
        ({"schema": 2}, "unsupported schema"),
        ({"stars": 3}, "Extra inputs"),
    ],
)
def test_invalid_package(changes: dict[str, object], match: str) -> None:
    assert_invalid(RegistryPackage, patched(PACKAGE, changes), match)


def test_versions_must_increase() -> None:
    RegistryPackage.model_validate(with_version(PACKAGE, "1.3.0-rc.1"))
    assert_invalid(RegistryPackage, with_version(PACKAGE, "1.1.0"), "strictly increasing")
    assert_invalid(RegistryPackage, with_version(PACKAGE, "1.2.0"), "strictly increasing")


@pytest.mark.parametrize(
    ("changes", "match"),
    [
        ({"packages.0.latest": "1.1.0"}, "latest must be the highest"),
        ({"packages.0.risk": "critical"}, "risk"),
        ({"packages.0.versions.0.published_at": "2027-02-10T10:00:00Z"}, "Extra inputs"),
        ({"packages": [INDEX["packages"][0], INDEX["packages"][0]]}, "duplicate package"),
        ({"core_latest": "1"}, "pattern"),
    ],
)
def test_invalid_index(changes: dict[str, object], match: str) -> None:
    assert_invalid(RegistryIndex, patched(INDEX, changes), match)


def test_registry_update_rules() -> None:
    old = RegistryPackage.model_validate(PACKAGE)
    added = RegistryPackage.model_validate(with_version(PACKAGE, "1.3.0"))
    assert check_registry_update(old, added) == []
    assert check_registry_update(None, old) == []
    assert check_registry_update(added, old) == ["published version 1.3.0 cannot be removed"]
    changed = RegistryPackage.model_validate(patched(PACKAGE, {"versions.0.sha256": SHA}))
    assert check_registry_update(old, changed) == ["published version 1.2.0 cannot be modified"]
    renamed = RegistryPackage.model_validate(patched(PACKAGE, {"kind": "tool"}))
    assert check_registry_update(old, renamed) == ["name and kind cannot change"]
    verified = RegistryPackage.model_validate(patched(PACKAGE, {"verified": True}))
    assert check_registry_update(old, verified) == [
        "verified/deprecated can only be changed by a maintainer"
    ]
    assert check_registry_update(old, verified, by_maintainer=True) == []
    assert check_registry_update(None, verified) == [
        "verified/deprecated can only be set by a maintainer"
    ]


def test_registry_update_rejects_older_new_version() -> None:
    old = RegistryPackage.model_validate(with_version(PACKAGE, "1.3.0"))
    data = with_version(PACKAGE, "1.2.5")
    data["versions"].append(old.model_dump(mode="json")["versions"][1])
    new = RegistryPackage.model_validate(data)
    assert check_registry_update(old, new) == ["new version 1.2.5 must be greater than 1.3.0"]

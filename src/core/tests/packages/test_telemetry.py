# SPDX-License-Identifier: AGPL-3.0-or-later
"""Opt-in install telemetry (CD-026): off by default, anonymous, monthly instance hash."""

import hashlib
from datetime import UTC, datetime
from typing import Any

import httpx2
import pytest

from dexterhouse import __version__
from dexterhouse.apps.packages.models import InstallStatus
from dexterhouse.apps.packages.services import telemetry

from .conftest import index_entry, run, sha_of

pytestmark = pytest.mark.django_db
REPO = "https://github.com/janedoe/dh-security-reviewer"
MARKETPLACE = "https://marketplace.example"


@pytest.fixture
def posts(monkeypatch) -> list[dict[str, Any]]:
    sent: list[dict[str, Any]] = []

    def post(url: str, *, json: dict[str, Any], timeout: float) -> httpx2.Response:
        sent.append({"url": url, **json})
        return httpx2.Response(204, request=httpx2.Request("POST", url))

    monkeypatch.setattr(telemetry.httpx2, "post", post)
    return sent


@pytest.fixture
def opted_in(settings, organization):
    settings.MARKETPLACE_URL = MARKETPLACE
    organization.settings = {**organization.settings, "telemetry": True}
    organization.save(update_fields=["settings"])
    return organization


def install_from_git(pkg_dir, fake_git, index_file, organization):
    src = pkg_dir()
    fake_git[REPO] = src
    index_file(index_entry("security-reviewer", REPO, [("1.0.0", "v1.0.0", sha_of(src))]))
    return run(f"git+{REPO}@v1.0.0", organization=organization)


def test_installation_id_is_created_once(settings):
    first = telemetry.installation_id()
    assert len(first) == 32
    assert telemetry.installation_id() == first
    assert (settings.PACKAGES_DIR / ".instance" / "installation_id").read_text() == first
    assert [p.name for p in (settings.PACKAGES_DIR / ".instance").iterdir()] == ["installation_id"]


def test_instance_hash_rotates_monthly():
    november = telemetry.instance_hash(datetime(2026, 11, 30, tzinfo=UTC))
    expected = hashlib.sha256(f"{telemetry.installation_id()}2026-11".encode()).hexdigest()
    assert november == expected
    assert telemetry.instance_hash(datetime(2026, 11, 1, tzinfo=UTC)) == november
    assert telemetry.instance_hash(datetime(2026, 12, 1, tzinfo=UTC)) != november


def test_successful_registry_install_is_reported(
    pkg_dir, fake_git, index_file, opted_in, posts, settings
):
    done = install_from_git(pkg_dir, fake_git, index_file, opted_in)
    assert done.status == InstallStatus.INSTALLED
    assert posts == [
        {
            "url": f"{MARKETPLACE}/api/v1/installs",
            "package": "security-reviewer",
            "version": "1.0.0",
            "core_version": __version__,
            "instance_hash": telemetry.instance_hash(),
        }
    ]


def test_off_by_default(pkg_dir, fake_git, index_file, organization, posts, settings):
    settings.MARKETPLACE_URL = MARKETPLACE
    assert "telemetry" not in organization.settings
    install_from_git(pkg_dir, fake_git, index_file, organization)
    assert posts == []


@pytest.mark.parametrize("change", ["no_url", "telemetry_string", "global"])
def test_no_op_cases(change, pkg_dir, fake_git, index_file, opted_in, posts, settings):
    kwargs: dict[str, Any] = {"organization": opted_in}
    if change == "no_url":
        settings.MARKETPLACE_URL = ""
    elif change == "telemetry_string":
        opted_in.settings = {"telemetry": "true"}
        opted_in.save(update_fields=["settings"])
    else:
        kwargs["organization"] = None
    done = install_from_git(pkg_dir, fake_git, index_file, **kwargs)
    assert done.status == InstallStatus.INSTALLED
    assert posts == []


def test_local_and_rejected_installs_are_not_reported(pkg_dir, opted_in, posts):
    assert run(str(pkg_dir()), organization=opted_in).status == InstallStatus.INSTALLED
    broken = pkg_dir(name="broken")
    (broken / "README.md").unlink()
    assert run(str(broken), organization=opted_in).status == InstallStatus.INCOMPATIBLE
    assert posts == []


def test_failures_are_only_logged(pkg_dir, fake_git, index_file, opted_in, monkeypatch):
    def fail(url: str, **kwargs: Any) -> httpx2.Response:
        raise httpx2.ConnectError("down")

    monkeypatch.setattr(telemetry.httpx2, "post", fail)
    done = install_from_git(pkg_dir, fake_git, index_file, opted_in)
    assert done.status == InstallStatus.INSTALLED
    assert telemetry.report_install(done.package_version) is False


def test_organization_setting_must_be_boolean(client):
    ok = client.patch("/api/v1/organization", {"settings": {"telemetry": True}}, format="json")
    assert ok.json()["settings"]["telemetry"] is True
    bad = client.patch("/api/v1/organization", {"settings": {"telemetry": "yes"}}, format="json")
    assert bad.status_code == 400

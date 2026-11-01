# SPDX-License-Identifier: AGPL-3.0-or-later
"""Real git: install from local bare repositories (`git+file://…@tag`), never the network."""

import hashlib
import subprocess

import pytest

from dexterhouse.apps.packages.models import InstallStatus
from dexterhouse.apps.packages.services import installer, store

from .conftest import git_repo, index_entry, run

pytestmark = [pytest.mark.slow, pytest.mark.django_db]


def archive_sha(repo, tag: str) -> str:
    """What the registry CI computes: `git archive --format=tar <tag> | sha256sum`."""
    data = subprocess.run(  # noqa: S603
        ["git", "-C", str(repo), "archive", "--format=tar", tag],  # noqa: S607
        capture_output=True,
        check=True,
    ).stdout
    return hashlib.sha256(data).hexdigest()


PUBLIC = "https://github.com/janedoe/dh-security-reviewer"


@pytest.fixture
def mirror(pkg_dir, tmp_path, monkeypatch):
    """A bare repository with tag v1.0.0, served for the public URL (no network)."""
    repo = git_repo(tmp_path / "repo.git", pkg_dir(), "v1.0.0")
    monkeypatch.setattr(installer, "_clone_url", lambda url: repo.as_uri())
    return repo


def test_install_from_a_git_tag_verified_against_the_index(mirror, index_file, organization):
    sha = archive_sha(mirror, "v1.0.0")
    index_file(index_entry("security-reviewer", PUBLIC, [("1.0.0", "v1.0.0", sha)]))
    done = run(f"git+{PUBLIC}@v1.0.0", organization=organization)
    assert done.status == InstallStatus.INSTALLED, done.errors
    assert done.package_version.sha256 == sha
    assert not (store.install_path(organization.id, "security-reviewer", "1.0.0") / ".git").exists()


def test_tampered_tag_is_rejected(mirror, index_file, organization):
    index_file(index_entry("security-reviewer", PUBLIC, [("1.0.0", "v1.0.0", "f" * 64)]))
    done = run(f"git+{PUBLIC}@v1.0.0", organization=organization)
    assert (done.status, done.reason) == (InstallStatus.INCOMPATIBLE, "hash")


def test_marketplace_install_through_a_mirror(mirror, index_file, organization):
    sha = archive_sha(mirror, "v1.0.0")
    index_file(index_entry("security-reviewer", PUBLIC, [("1.0.0", "v1.0.0", sha)]))
    done = run("security-reviewer", organization=organization)
    assert done.status == InstallStatus.INSTALLED, done.errors
    assert done.package_version.git_ref == "v1.0.0"


def test_missing_tag_fails_to_fetch(pkg_dir, tmp_path, organization):
    repo = git_repo(tmp_path / "repo.git", pkg_dir(), "v1.0.0")
    done = run(f"git+{repo.as_uri()}@v9.9.9", organization=organization)
    assert (done.status, done.reason) == (InstallStatus.FAILED, "fetch")
    assert "git clone failed" in done.errors[0]


def test_oversized_archive_is_refused(pkg_dir, tmp_path, organization, monkeypatch):
    repo = git_repo(tmp_path / "repo.git", pkg_dir(), "v1.0.0")
    monkeypatch.setattr(store, "MAX_PACKAGE_BYTES", 100)
    done = run(f"git+{repo.as_uri()}@v1.0.0", organization=organization)
    assert "limit 100" in done.errors[0]

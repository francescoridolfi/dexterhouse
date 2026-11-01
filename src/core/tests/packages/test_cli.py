# SPDX-License-Identifier: AGPL-3.0-or-later
"""`dexterhouse pkg …` with Typer's runner (in-process, test database)."""

import pytest
from typer.testing import CliRunner

from dexterhouse.apps.packages.models import Package
from dexterhouse.cli.main import app

runner = CliRunner()


def invoke(*args: str, input: str | None = None):  # type: ignore[no-untyped-def]
    return runner.invoke(app, list(args), input=input)


@pytest.mark.parametrize("kind", ["agent", "tool", "process"])
def test_init_creates_a_valid_package(tmp_path, kind):
    result = invoke("pkg", "init", "my-thing", "--kind", kind, "--dir", str(tmp_path))
    assert result.exit_code == 0, result.output
    checked = invoke("pkg", "validate", str(tmp_path / "my-thing"))
    assert checked.exit_code == 0, checked.output
    assert "valid" in checked.output


def test_init_and_validate_errors(tmp_path):
    assert invoke("pkg", "init", "Bad_Name", "--dir", str(tmp_path)).exit_code == 2
    assert invoke("pkg", "init", "good-name", "--kind", "x", "--dir", str(tmp_path)).exit_code == 2
    invoke("pkg", "init", "good-name", "--dir", str(tmp_path))
    assert invoke("pkg", "init", "good-name", "--dir", str(tmp_path)).exit_code == 1
    (tmp_path / "good-name" / "agent.yaml").write_text("schema: 1\n")
    result = invoke("pkg", "validate", str(tmp_path / "good-name"))
    assert result.exit_code == 1
    assert "invalid" in result.output


def test_version_and_help():
    assert "dexterhouse 0.1.0" in invoke("--version").output
    assert invoke().exit_code in (0, 2)


@pytest.mark.django_db
def test_install_list_disable_enable_remove(pkg_dir, organization):
    src = pkg_dir()
    result = invoke("pkg", "install", str(src), "--org", organization.slug)
    assert result.exit_code == 0, result.output
    assert "installed security-reviewer@1.0.0 (agent, local)" in result.output
    listed = invoke("pkg", "list", "--org", organization.slug, "--kind", "agent").output
    assert "security-reviewer" in listed
    assert "analyst" in listed
    assert "security-reviewer" not in invoke("pkg", "list").output
    assert invoke("pkg", "disable", "security-reviewer", "--org", organization.slug).exit_code == 0
    assert invoke("pkg", "disable", "security-reviewer", "--org", organization.slug).exit_code == 1
    assert invoke("pkg", "enable", "security-reviewer", "--org", organization.slug).exit_code == 0
    removed = invoke("pkg", "remove", "security-reviewer", "--org", organization.slug)
    assert "removed" in removed.output
    assert invoke("pkg", "remove", "security-reviewer", "--org", organization.slug).exit_code == 1
    assert invoke("pkg", "list", "--org", "nope").exit_code == 2


@pytest.mark.django_db
def test_install_global_with_consent_flag(pkg_dir):
    src = pkg_dir(name="git-tools", kind="tool")
    result = invoke("pkg", "install", str(src), "--confirm-permissions")
    assert result.exit_code == 0, result.output
    assert "git.push (high)" in result.output
    package = Package.objects.get(name="git-tools", organization__isnull=True)
    assert package.status == "installed"


@pytest.mark.django_db
def test_install_without_consent_declines(pkg_dir):
    src = pkg_dir(name="git-tools", kind="tool")
    result = invoke("pkg", "install", str(src))
    assert result.exit_code == 3
    assert "--confirm-permissions" in result.output
    assert not Package.objects.filter(name="git-tools", deleted_at__isnull=True).exists()


@pytest.mark.django_db
def test_install_errors(pkg_dir, tmp_path):
    bad = pkg_dir()
    (bad / "agent.yaml").write_text("schema: 1\n")
    result = invoke("pkg", "install", str(bad))
    assert result.exit_code == 1
    assert "incompatible (schema)" in result.output
    assert invoke("pkg", "install", "git+https://h/o/r").exit_code == 2

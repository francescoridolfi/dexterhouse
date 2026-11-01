# SPDX-License-Identifier: AGPL-3.0-or-later
"""Built-in sync, the management command, store helpers, the registry index client."""

import io
import json
import shutil
import tarfile
from pathlib import Path

import pytest
from django.core.management import CommandError, call_command

from dexterhouse.apps.events.models import Event
from dexterhouse.apps.packages.models import Package
from dexterhouse.apps.packages.services import index as registry
from dexterhouse.apps.packages.services import store, updates
from dexterhouse.apps.packages.services.builtin import builtin_folders, sync_builtin

from .conftest import index_entry, run, write_package


@pytest.mark.django_db
def test_sync_is_idempotent_and_follows_the_builtin_folder(settings, tmp_path):
    base = tmp_path / "builtin"
    shutil.copytree(Path(settings.BUILTIN_DIR) / "processes", base / "processes")
    first = sync_builtin(base)
    assert first.unchanged == ["code-review-only", "software-house-default"]  # same content
    assert first.removed
    assert "analyst" in first.removed
    assert Package.objects.get(name="analyst").deleted_at is not None
    process = base / "processes" / "code-review-only" / "README.md"
    process.write_text(process.read_text() + "\nChanged.\n")
    second = sync_builtin(base)
    assert second.installed == ["code-review-only"]
    (base / "processes" / "code-review-only" / "process.yaml").write_text("schema: 1\n")
    third = sync_builtin(base)
    assert "code-review-only" in third.rejected
    # the previous good version stays enabled
    assert Package.objects.get(name="code-review-only").enabled_version is not None


@pytest.mark.django_db
def test_a_builtin_in_use_is_only_disabled(settings, tmp_path, project):
    from dexterhouse.apps.agents.services import roster

    roster.ensure_agent(project, "analyst")
    project.status = "running"
    project.save()
    (tmp_path / "empty").mkdir()
    sync_builtin(tmp_path / "empty")
    analyst = Package.objects.get(name="analyst")
    assert (analyst.deleted_at, analyst.status) == (None, "disabled")


@pytest.mark.django_db
def test_management_command(settings, tmp_path, capsys):
    call_command("packages", "sync-builtin")
    assert "12 unchanged" in capsys.readouterr().out
    call_command("packages", "check-compat")
    broken = tmp_path / "b" / "agents" / "broken"
    write_package(broken, name="broken")
    (broken / "agent.yaml").write_text("schema: 1\n")
    settings.BUILTIN_DIR = tmp_path / "b"
    with pytest.raises(CommandError, match="1 built-in package"):
        call_command("packages", "sync-builtin")
    assert builtin_folders(tmp_path / "missing") == []


def test_parse_git_source(settings):
    assert store.parse_git_source("git+https://github.com/o/r@v1.2.0") == store.GitSource(
        "https://github.com/o/r", "v1.2.0"
    )
    assert store.parse_git_source("git+https://h/o/r@v1").display == "git+https://h/o/r@v1"
    for bad in (
        "https://h/o/r@v1",
        "git+https://h/o/r",
        "git+https://u:p@h/o/r@v1",
        "git+ssh://h/o/r@v1",
        "git+https://h/o/r@-x",
        "git+https://h/o/r@a/b",
    ):
        with pytest.raises(store.FetchError):
            store.parse_git_source(bad)
    assert store.parse_git_source("git+file:///tmp/repo@v1").url == "file:///tmp/repo"
    settings.PACKAGES_ALLOW_LOCAL = False
    with pytest.raises(store.FetchError):
        store.parse_git_source("git+file:///tmp/repo@v1")


def _tar(*members: tarfile.TarInfo, data: bytes = b"x") -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as tar:
        for member in members:
            tar.addfile(member, io.BytesIO(data) if member.isfile() else None)
    return buffer.getvalue()


def test_extract_tar_refuses_links_and_traversal(tmp_path):
    link = tarfile.TarInfo("evil")
    link.type, link.linkname = tarfile.SYMTYPE, "/etc/passwd"
    with pytest.raises(store.FetchError, match="unsupported entry"):
        store.extract_tar(_tar(link), tmp_path / "a")
    escape = tarfile.TarInfo("../outside")
    escape.size = 1
    with pytest.raises(store.FetchError, match="invalid archive"):
        store.extract_tar(_tar(escape), tmp_path / "b")
    big = tarfile.TarInfo("big")
    big.size = store.MAX_PACKAGE_BYTES + 1
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as tar:
        tar.addfile(big, io.BytesIO(b"\0" * big.size))
    with pytest.raises(store.FetchError, match="larger"):
        store.extract_tar(buffer.getvalue(), tmp_path / "c")


def test_copy_folder_hash_and_discard(tmp_path, settings, monkeypatch):
    src = write_package(tmp_path / "src")
    (src / ".git").mkdir()
    (src / ".git" / "HEAD").write_text("ref")
    dest = Path(settings.PACKAGES_DIR) / "x"
    sha = store.copy_folder(src, dest)
    assert not (dest / ".git").exists()
    assert sha == store.tree_hash(src)
    (src / "README.md").write_text("changed")
    assert store.tree_hash(src) != sha
    monkeypatch.setattr(store, "MAX_PACKAGE_BYTES", 10)
    with pytest.raises(store.FetchError, match="limit"):
        store.copy_folder(src, dest)
    store.discard(tmp_path / "src")  # outside PACKAGES_DIR: untouched
    assert src.exists()
    store.discard(dest)
    assert not dest.exists()
    store.discard(None)


def test_fetch_git_without_git(monkeypatch, tmp_path):
    monkeypatch.setattr(store.shutil, "which", lambda name: None)
    with pytest.raises(store.FetchError, match="not installed"):
        store.fetch_git(store.GitSource("https://h/o/r", "v1"), tmp_path / "d")


def test_index_client_cache_and_fallback(index_file, settings, monkeypatch):
    path = index_file(index_entry("a-pkg", "https://github.com/o/a", [("1.0.0", "v1", "a" * 64)]))
    snapshot = registry.get_index()
    assert snapshot.source == "index"
    assert snapshot.get("a-pkg").latest == "1.0.0"
    assert snapshot.get("nope") is None
    assert registry.get_index() is snapshot  # memory cache
    path.write_text("{broken")
    fallback = registry.get_index(refresh=True)
    assert fallback.source == "cache"
    assert fallback.get("a-pkg")
    settings.REGISTRY_INDEX_URL = "http://insecure.example/index.json"
    registry.clear_cache()
    assert registry.get_index().source == "cache"
    (Path(settings.PACKAGES_DIR) / ".registry" / "index.json").unlink()
    registry.clear_cache()
    with pytest.raises(registry.IndexUnavailableError):
        registry.get_index()


def test_index_over_https(settings, monkeypatch):
    calls = []

    class Response:
        content = json.dumps(
            {
                "schema": 1,
                "generated_at": "2026-11-01T00:00:00Z",
                "core_latest": "0.1.0",
                "packages": [],
            }
        ).encode()

        def raise_for_status(self):
            return None

    monkeypatch.setattr(registry.httpx2, "get", lambda url, **kw: calls.append(url) or Response())
    settings.REGISTRY_INDEX_URL = "https://registry.example/index.json"
    assert registry.get_index().index.packages == []
    assert calls == ["https://registry.example/index.json"]


def test_version_helpers():
    entry = registry.RegistryIndex.model_validate(
        {
            "schema": 1,
            "generated_at": "2026-11-01T00:00:00Z",
            "core_latest": "0.1.0",
            "packages": [
                index_entry(
                    "a-pkg",
                    "https://github.com/o/a",
                    [("1.0.0", "v1", "a" * 64), ("2.0.0", "v2", "b" * 64)],
                )
            ],
        }
    ).packages[0]
    entry.versions[1].compat_core = ">=5.0"
    assert registry.pick_version(entry).version == "1.0.0"
    assert registry.pick_version(entry, "2.0.0").version == "2.0.0"
    assert registry.pick_version(entry, "3.0.0") is None
    assert registry.compatible("not a range") is False
    assert registry.same_repo("https://GitHub.com/o/r.git/", "https://github.com/o/r")
    assert not registry.same_repo("https://github.com/o/r", "https://github.com/o/x")


@pytest.mark.django_db
def test_update_available_is_emitted_once(pkg_dir, fake_git, index_file, organization):
    repo = "https://github.com/janedoe/dh-security-reviewer"
    src = pkg_dir()
    fake_git[repo] = src
    from .conftest import sha_of

    index_file(index_entry("security-reviewer", repo, [("1.0.0", "v1.0.0", sha_of(src))]))
    run(f"git+{repo}@v1.0.0", organization=organization)
    assert updates.check_updates() == []
    index_file(
        index_entry(
            "security-reviewer",
            repo,
            [("1.0.0", "v1.0.0", sha_of(src)), ("1.2.0", "v1.2.0", "c" * 64)],
        )
    )
    assert updates.check_updates() == ["security-reviewer@1.2.0"]
    assert updates.check_updates() == []
    event = Event.objects.get(type="package.update_available")
    assert event.payload | {"package_id": None} == {
        "package_id": None,
        "name": "security-reviewer",
        "current": "1.0.0",
        "latest": "1.2.0",
        "compat_ok": True,
    }


@pytest.mark.django_db
def test_update_check_without_index(settings, tmp_path):
    assert updates.check_updates() == []
    settings.REGISTRY_INDEX_URL = (tmp_path / "missing.json").as_uri()
    assert updates.check_updates() == []


@pytest.mark.django_db
def test_tasks(pkg_dir):
    from dexterhouse.apps.packages import tasks
    from dexterhouse.apps.packages.services import installer

    install = installer.request_install(organization=None, source=str(pkg_dir()))
    assert tasks.run_install(str(install.id)) == "installed"
    assert tasks.collect_unused() == 0
    assert tasks.check_updates() == []

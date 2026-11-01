# SPDX-License-Identifier: AGPL-3.0-or-later
import subprocess

import pytest
from django.core.exceptions import ImproperlyConfigured

from dexterhouse.apps.projects.services import validation
from dexterhouse.apps.projects.services.projects import create_project, update_project
from dexterhouse.apps.workflows import registry, tasks
from dexterhouse.common import crypto
from dexterhouse.common.api.problems import flatten_errors
from dexterhouse.common.errors import ValidationFailedError


def test_git_ls_remote_sends_the_token_via_env_only(monkeypatch):
    calls = []

    def fake_run(argv, **kwargs):
        calls.append((argv, kwargs["env"]))
        return subprocess.CompletedProcess(argv, 0 if "ok" in argv[-1] else 128)

    monkeypatch.setattr(validation.shutil, "which", lambda _: "/usr/bin/git")
    monkeypatch.setattr(validation.subprocess, "run", fake_run)
    assert validation.git_ls_remote("https://example.com/ok.git", "secret") is None
    argv, env = calls[0]
    assert "secret" not in " ".join(argv)
    assert env["GIT_CONFIG_KEY_0"] == "http.extraHeader"
    assert validation.git_ls_remote("https://example.com/no.git", None) is not None
    assert "GIT_CONFIG_COUNT" not in calls[1][1]


def test_git_ls_remote_timeout_and_missing_git(monkeypatch):
    def slow(argv, **kwargs):
        raise subprocess.TimeoutExpired(argv, 1)

    monkeypatch.setattr(validation.shutil, "which", lambda _: "/usr/bin/git")
    monkeypatch.setattr(validation.subprocess, "run", slow)
    assert "in time" in validation.git_ls_remote("https://example.com/x.git", None)
    monkeypatch.setattr(validation.shutil, "which", lambda _: None)
    assert "not available" in validation.git_ls_remote("https://example.com/x.git", None)


def test_flatten_nested_errors():
    detail = {"a": {"b": ["bad"]}, "c": [{"d": ["x"]}], "non_field_errors": ["top"], "e": "s"}
    assert flatten_errors(detail) == [
        {"field": "a.b", "message": "bad"},
        {"field": "c[0].d", "message": "x"},
        {"field": "", "message": "top"},
        {"field": "e", "message": "s"},
    ]


def test_crypto_requires_a_key(settings):
    settings.FERNET_KEY = ""
    with pytest.raises(ImproperlyConfigured):
        crypto.encrypt("x")


@pytest.mark.django_db
def test_registry_lists_the_installed_processes_only():
    from dexterhouse.apps.packages.models import Package
    from dexterhouse.apps.packages.services.lifecycle import disable

    assert set(registry.installed_processes()) == {"code-review-only", "software-house-default"}
    disable(Package.objects.get(name="code-review-only"))
    assert set(registry.installed_processes()) == {"software-house-default"}
    assert registry.get_process("code-review-only") is None
    assert registry.get_process("code-review-only", version="1.0.0").version == "1.0.0"


@pytest.mark.django_db
def test_update_project_in_draft(organization, user):
    project = create_project(organization, user, {"name": "P", "brief": "b", "budget": "1"})
    update_project(project, user, {"process": "code-review-only", "remote_token": "t"})
    assert project.process_name == "code-review-only"
    assert crypto.decrypt(project.remote_token) == "t"
    with pytest.raises(ValidationFailedError):
        update_project(project, user, {"process": "nope"})
    update_project(project, user, {"stack": None, "remote_token": None})
    assert project.remote_token is None


@pytest.mark.django_db
def test_celery_tasks_delegate_to_services(monkeypatch):
    seen = []
    monkeypatch.setattr(tasks.steps, "run_step", seen.append)
    monkeypatch.setattr(tasks.steps, "reconcile", lambda: 7)
    tasks.run_step("abc")
    assert seen == ["abc"]
    assert tasks.reconcile() == 7

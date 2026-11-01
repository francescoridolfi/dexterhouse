# SPDX-License-Identifier: AGPL-3.0-or-later
"""Agents runtime fixtures: a test agent package, a real stdio MCP echo server, fake LLM."""

import json
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from dexterhouse.apps.agents.models import AgentInstance
from dexterhouse.apps.agents.services import create_agent_instance
from dexterhouse.apps.gateway.models import ModelProfile
from dexterhouse.apps.gateway.providers import PROVIDERS, FakeProvider
from dexterhouse.apps.gateway.providers.fake import FakeResponse, FakeToolCall
from dexterhouse.apps.packages.models import Package
from tests.conftest import install_test_packages

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def tool_dirs(tmp_path: Path, settings, db) -> Path:
    """A private copy of the echo tool package, installed from it (its call log is per test)."""
    root = tmp_path / "tools"
    shutil.copytree(FIXTURES / "tools", root)
    settings.PACKAGES_DIR = tmp_path / "packages"
    install_test_packages(root)
    return root


def installed_root(name: str) -> Path:
    """Where the enabled version of package `name` is installed."""
    package = Package.objects.get(name=name, deleted_at__isnull=True)
    return Path(package.enabled_version.install_path)


@pytest.fixture
def echo_log(tool_dirs: Path) -> Callable[[], list[str]]:
    log = installed_root("echo-tools") / "calls.log"
    return lambda: log.read_text(encoding="utf-8").splitlines() if log.exists() else []


@pytest.fixture
def fake_profiles(organization) -> None:
    for profile in ("strong", "balanced", "fast"):
        ModelProfile.objects.create(
            organization=organization, profile=profile, provider="fake", model="fake-model"
        )
    ModelProfile.objects.create(
        organization=organization, profile="embed", provider="fake", model="hash-1024"
    )


@pytest.fixture
def script(monkeypatch) -> Callable[..., FakeProvider]:
    """Make the `fake` provider serve the given responses, in order, for the whole test."""

    def install(*responses: FakeResponse) -> FakeProvider:
        provider = FakeProvider(list(responses))
        monkeypatch.setitem(PROVIDERS, "fake", lambda config: provider)
        return provider

    return install


@pytest.fixture
def agent(organization, project, fake_profiles, tool_dirs) -> AgentInstance:
    return create_agent_instance(
        organization_id=organization.id,
        project_id=project.id,
        package_path=str(FIXTURES / "agents" / "test-analyst"),
    )


def call(name: str, call_id: str = "c1", **args: Any) -> FakeToolCall:
    return FakeToolCall(id=call_id, name=name, args=args)


def final(**overrides: Any) -> FakeResponse:
    output = {
        "status": "done",
        "summary": "Wrote the requirements.",
        "artifacts": [{"kind": "requirements", "name": "requirements.md", "content": "# R\n"}],
    }
    return FakeResponse(text="Here it is.\n" + json.dumps(output | overrides))

# SPDX-License-Identifier: AGPL-3.0-or-later
"""Agents runtime fixtures: a test agent package, a real stdio MCP echo server, fake LLM."""

import json
import shutil
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from dexterhouse.apps.agents.models import AgentInstance
from dexterhouse.apps.agents.services import create_agent_instance
from dexterhouse.apps.gateway.models import ModelProfile
from dexterhouse.apps.gateway.providers import PROVIDERS, FakeProvider
from dexterhouse.apps.gateway.providers.fake import FakeResponse, FakeToolCall

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def tool_dirs(tmp_path: Path, settings) -> Path:
    """A private copy of the echo tool package (its call log is per test)."""
    root = tmp_path / "tools"
    shutil.copytree(FIXTURES / "tools", root)
    settings.AGENTS_TOOL_PACKAGE_DIRS = [str(root)]
    return root


@pytest.fixture
def echo_log(tool_dirs: Path) -> Callable[[], list[str]]:
    log = tool_dirs / "echo-tools" / "calls.log"
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
def agent(organization, fake_profiles, tool_dirs) -> AgentInstance:
    return create_agent_instance(
        organization_id=organization.id,
        project_id=uuid.uuid4(),
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

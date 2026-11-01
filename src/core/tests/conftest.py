# SPDX-License-Identifier: AGPL-3.0-or-later
from pathlib import Path

import pytest

from dexterhouse.apps.accounts.models import Membership, Organization, Role, User
from tests.live_runner import (  # noqa: F401 - session fixtures of the real runner (Docker)
    docker_client,
    egress_proxy,
    live_runner,
    runner_settings,
)

#: One minimal agent package per built-in role (the real ones are in `src/builtin/agents`).
TEAM_PACKAGES = Path(__file__).parent / "fixtures" / "agent_packages"


@pytest.fixture
def organization(db) -> Organization:
    # get_or_create: transactional tests flush the seeded row.
    return Organization.objects.get_or_create(slug="default", defaults={"name": "Default"})[0]


@pytest.fixture
def user(db, organization: Organization) -> User:
    user = User.objects.create_user(username="ada", password="pw-for-tests-only")
    Membership.objects.create(user=user, organization=organization, role=Role.OWNER)
    return user


@pytest.fixture
def project(organization, user):
    """A draft project (a real row: agents, LLM calls and memory point to it)."""
    from dexterhouse.apps.projects.services.projects import create_project

    return create_project(
        organization, user, {"name": "GymBook", "brief": "A gym app.", "budget": "5"}
    )


@pytest.fixture
def team_packages(settings) -> Path:
    """Agent packages are looked up in the test team fixtures."""
    settings.AGENTS_PACKAGE_DIRS = [str(TEAM_PACKAGES)]
    return TEAM_PACKAGES


@pytest.fixture
def client(user):
    """DRF client logged in (session) as the owner `ada`."""
    from rest_framework.test import APIClient

    api = APIClient()
    api.force_login(user)
    return api


@pytest.fixture
def make_member(organization, django_user_model):
    """Create a user with `role` in the organization and return a logged-in client."""
    from rest_framework.test import APIClient

    def make(role: str, username: str | None = None):
        member = django_user_model.objects.create_user(username=username or role)
        Membership.objects.create(user=member, organization=organization, role=role)
        api = APIClient()
        api.force_login(member)
        return api

    return make


@pytest.fixture(autouse=True)
def _reset_gateway_state():
    """Circuit breakers and CLI slots live in Redis: start every test closed and empty."""
    from dexterhouse.apps.events.services.streams import get_client

    client = get_client()
    keys = list(client.scan_iter("dh:gateway:*"))
    if keys:
        client.delete(*keys)


@pytest.fixture
def no_packages(settings, tmp_path) -> None:
    """No agent package at all: every role is hired as a placeholder."""
    settings.AGENTS_PACKAGE_DIRS = [str(tmp_path / "no-packages")]


@pytest.fixture
def builtin_runtime(settings, organization, monkeypatch):
    """`AgentsTurnRunner` + the built-in agent packages + the demo responder (no LLM).

    For transactional tests: the stdio MCP servers read the test database through the
    environment; `run_step` is not sent anywhere, `drain` runs the steps.
    """
    from django.db import connection

    from dexterhouse.apps.workflows import tasks
    from tests.workflows.agents_runtime import use_fake_profiles

    db = connection.settings_dict
    monkeypatch.setenv(
        "DATABASE_URL", f"postgres://{db['USER']}@{db['HOST']}:{db['PORT']}/{db['NAME']}"
    )
    monkeypatch.setenv("DJANGO_SETTINGS_MODULE", "dexterhouse.settings.test")
    monkeypatch.setattr(tasks.run_step, "delay", lambda step_id: None)
    settings.WORKFLOWS_TURN_RUNNER = "dexterhouse.apps.workflows.runners.agents.AgentsTurnRunner"
    settings.GATEWAY_FAKE_RESPONDER = "dexterhouse.apps.agents.demo.respond"
    settings.AGENTS_DEMO_SCRIPT = {}
    use_fake_profiles(organization)


class FakeRunnerClient:
    """Records the runner messages; answers from `results` (task -> ToolResult or callable)."""

    inline = False

    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []
        self.sent: list[tuple[str, object]] = []
        self.results: dict[str, object] = {}

    def call(self, task, message, timeout_s=None):
        from dexterhouse_schema.runner import ToolResult

        self.calls.append((task, message))
        answer = self.results.get(task, ToolResult(ok=True, data={}))
        return answer(message) if callable(answer) else answer

    def send(self, task, message) -> None:
        self.sent.append((task, message))

    def tasks(self) -> list[str]:
        return [t for t, _ in self.calls]


@pytest.fixture
def runner_client(monkeypatch) -> FakeRunnerClient:
    """Replace the runner client (`settings.RUNNER_CLIENT`) by a recorder."""
    from dexterhouse.apps.workspaces import client as client_module

    fake = FakeRunnerClient()
    monkeypatch.setattr(client_module, "import_string", lambda path: lambda: fake)
    return fake

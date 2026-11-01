# SPDX-License-Identifier: AGPL-3.0-or-later
import shutil
from pathlib import Path

import pytest

from dexterhouse.apps.accounts.models import Membership, Organization, Role, User

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


def install_test_packages(base: Path, *, replace: bool = False) -> list[str]:
    """Install every package folder under `base` from its path (global, source `local`).

    `replace` first disables the enabled agent packages whose role a folder provides (the
    built-in team); otherwise a folder whose role is taken is rejected and skipped.
    Returns the names installed.
    """
    import yaml

    from dexterhouse.apps.packages.models import InstallStatus, Package
    from dexterhouse.apps.packages.services import installer, lifecycle
    from dexterhouse.apps.packages.services.builtin import ensure_builtin
    from dexterhouse.common.errors import ConflictError

    ensure_builtin()
    folders = sorted(p for p in base.iterdir() if (p / "dexterhouse.yaml").is_file())
    if replace:
        roles = {
            yaml.safe_load((f / "agent.yaml").read_text())["role"]
            for f in folders
            if (f / "agent.yaml").is_file()
        }
        for package in Package.objects.filter(
            kind="agent", enabled_version__isnull=False, deleted_at__isnull=True
        ).select_related("enabled_version"):
            if package.enabled_version.definition.get("role") in roles:
                lifecycle.disable(package, reason="replaced by test fixtures")
    installed = []
    for folder in folders:
        name = yaml.safe_load((folder / "dexterhouse.yaml").read_text())["name"]
        parked = Package.objects.filter(
            organization__isnull=True, name=name, status="disabled", source="local"
        ).first()
        if parked is not None and parked.source_url == str(folder.resolve()):
            try:  # installed (disabled) at session start: enabling is much cheaper
                lifecycle.enable(parked)
                installed.append(name)
            except ConflictError:
                pass
            continue
        done = installer.install(organization=None, source=str(folder))
        if done.status == InstallStatus.INSTALLED:
            installed.append(done.name)
    return installed


def _park_test_team() -> None:
    """Install the test team once, disabled: `team_packages` only has to enable it."""
    from dexterhouse.apps.packages.models import Package
    from dexterhouse.apps.packages.services import lifecycle

    names = install_test_packages(TEAM_PACKAGES, replace=True)
    for package in Package.objects.filter(name__in=names, organization__isnull=True):
        lifecycle.disable(package, reason="test team, enabled by team_packages")
    for package in Package.objects.filter(source="builtin", kind="agent", status="disabled"):
        lifecycle.enable(package)


@pytest.fixture(scope="session")
def django_db_setup(django_db_setup, django_db_blocker):
    """Install the built-in packages once (tests roll back to this state)."""
    from django.conf import settings

    from dexterhouse.apps.packages.services.builtin import sync_builtin

    with django_db_blocker.unblock():
        sync_builtin()
        _park_test_team()
    yield
    shutil.rmtree(settings.PACKAGES_DIR, ignore_errors=True)


@pytest.fixture
def team_packages(db) -> Path:
    """The test team fixtures replace the built-in agents (installed from their folders)."""
    install_test_packages(TEAM_PACKAGES, replace=True)
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
def no_packages(db) -> None:
    """No agent package at all: every role is hired as a placeholder."""
    from dexterhouse.apps.packages.models import Package
    from dexterhouse.apps.packages.services.builtin import ensure_builtin

    ensure_builtin()
    Package.objects.filter(kind="agent").update(enabled_version=None, status="disabled")


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

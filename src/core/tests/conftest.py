# SPDX-License-Identifier: AGPL-3.0-or-later
from pathlib import Path

import pytest

from dexterhouse.apps.accounts.models import Membership, Organization, Role, User

#: One minimal agent package per built-in role (E-04 ships the real ones).
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

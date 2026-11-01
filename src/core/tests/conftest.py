# SPDX-License-Identifier: AGPL-3.0-or-later
import pytest

from dexterhouse.apps.accounts.models import Membership, Organization, Role, User


@pytest.fixture
def organization(db) -> Organization:
    return Organization.objects.get(slug="default")


@pytest.fixture
def user(db, organization: Organization) -> User:
    user = User.objects.create_user(username="ada", password="pw-for-tests-only")
    Membership.objects.create(user=user, organization=organization, role=Role.OWNER)
    return user

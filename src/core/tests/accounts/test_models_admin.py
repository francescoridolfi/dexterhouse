# SPDX-License-Identifier: AGPL-3.0-or-later
import pytest
from django.db import IntegrityError, transaction
from django.urls import reverse

from dexterhouse.apps.accounts.models import ApiToken, Membership, Organization, Role, User
from dexterhouse.apps.accounts.services.tokens import create_token

pytestmark = pytest.mark.django_db


def test_default_organization_is_seeded():
    org = Organization.objects.get(slug="default")
    assert str(org) == "default"
    assert org.id.version == 7


def test_membership_unique_and_role_checked(organization, user):
    with pytest.raises(IntegrityError), transaction.atomic():
        Membership.objects.create(user=user, organization=organization, role=Role.ADMIN)
    other = User.objects.create_user(username="bob")
    with pytest.raises(IntegrityError), transaction.atomic():
        Membership.objects.create(user=other, organization=organization, role="emperor")
    membership = Membership.objects.get(user=user)
    assert str(membership).endswith(":owner")


@pytest.mark.parametrize("name", ["accounts_organization", "accounts_user", "accounts_apitoken"])
def test_admin_changelists(admin_client, name, organization, user):
    create_token(organization=organization, user=user, name="ci", scopes=[])
    response = admin_client.get(reverse(f"admin:{name}_changelist"))
    assert response.status_code == 200


def test_tokens_cannot_be_added_from_admin(admin_client):
    assert admin_client.get(reverse("admin:accounts_apitoken_add")).status_code == 403


def test_token_str(organization, user):
    token, _ = create_token(organization=organization, user=user, name="ci", scopes=[])
    assert str(ApiToken.objects.get(pk=token.pk)) == "ci"

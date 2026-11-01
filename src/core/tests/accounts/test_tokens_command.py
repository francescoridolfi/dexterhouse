# SPDX-License-Identifier: AGPL-3.0-or-later
import io
import uuid

import pytest
from django.core.management import CommandError, call_command

from dexterhouse.apps.accounts.models import ApiToken
from dexterhouse.apps.accounts.services.tokens import resolve_token

pytestmark = pytest.mark.django_db


def run(*args: str) -> str:
    out = io.StringIO()
    call_command("tokens", *args, stdout=out, stderr=io.StringIO())
    return out.getvalue()


def test_create_list_revoke(user):
    plaintext = run(
        "create",
        "--user",
        "ada",
        "--name",
        "ci",
        "--scopes",
        "projects:read,events:read",
        "--days",
        "30",
    ).strip()
    token = resolve_token(plaintext)
    assert token is not None
    assert token.scopes == ["events:read", "projects:read"]
    assert token.expires_at is not None
    assert "ci  ada  events:read,projects:read  last used" in run("list")
    assert run("revoke", str(token.id)).startswith("revoked")
    assert not ApiToken.objects.exists()


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (["create", "--user", "nobody", "--name", "x", "--scopes", "projects:read"], "member"),
        (["create", "--user", "ada", "--name", "x", "--scopes", "root"], "unknown scopes"),
        (["revoke", str(uuid.uuid4())], "no token"),
    ],
)
def test_errors(user, args, message):
    with pytest.raises(CommandError, match=message):
        run(*args)

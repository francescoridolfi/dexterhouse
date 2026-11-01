# SPDX-License-Identifier: AGPL-3.0-or-later
"""`manage.py tokens create|list|revoke`: API tokens for scripts and CI (docs/api.md).

The plaintext is printed once by `create` and never stored. A token acts as its user within
one organization and only with its scopes; the user's role still applies.
"""

from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.utils import timezone

from dexterhouse.apps.accounts.models import ApiToken, Membership, Scope
from dexterhouse.apps.accounts.services.tokens import InvalidScopeError, create_token


class Command(BaseCommand):
    help = "Create, list or revoke API tokens."

    def add_arguments(self, parser: CommandParser) -> None:
        sub = parser.add_subparsers(dest="action", required=True)
        create = sub.add_parser("create")
        create.add_argument("--user", required=True)
        create.add_argument("--org", default=settings.DEFAULT_ORG_SLUG)
        create.add_argument("--name", required=True)
        create.add_argument(
            "--scopes", required=True, help=f"comma separated: {', '.join(Scope.values)}"
        )
        create.add_argument("--days", type=int, default=0, help="expiry; 0 = never")
        listing = sub.add_parser("list")
        listing.add_argument("--org", default=settings.DEFAULT_ORG_SLUG)
        revoke = sub.add_parser("revoke")
        revoke.add_argument("token_id")

    def handle(self, *args: object, **options: object) -> None:
        getattr(self, f"_{options['action']}")(options)

    def _create(self, options: dict[str, object]) -> None:
        membership = (
            Membership.objects.select_related("organization", "user")
            .filter(user__username=options["user"], organization__slug=options["org"])
            .first()
        )
        if membership is None:
            raise CommandError(f"{options['user']} is not a member of {options['org']}")
        days = int(str(options["days"]))
        scopes = [s.strip() for s in str(options["scopes"]).split(",") if s.strip()]
        try:
            token, plaintext = create_token(
                organization=membership.organization,
                user=membership.user,
                name=str(options["name"]),
                scopes=scopes,
                expires_at=timezone.now() + timedelta(days=days) if days > 0 else None,
            )
        except InvalidScopeError as exc:
            raise CommandError(str(exc)) from exc
        self.stderr.write(f"token {token.id} ({', '.join(token.scopes)}); shown only once:")
        self.stdout.write(plaintext)

    def _list(self, options: dict[str, object]) -> None:
        rows = ApiToken.objects.filter(organization__slug=options["org"]).select_related("user")
        for token in rows.order_by("created_at"):
            used = token.last_used_at.isoformat() if token.last_used_at else "never"
            self.stdout.write(
                f"{token.id}  {token.name}  {token.user.get_username()}  "
                f"{','.join(token.scopes)}  last used {used}"
            )

    def _revoke(self, options: dict[str, object]) -> None:
        deleted, _ = ApiToken.objects.filter(pk=options["token_id"]).delete()
        if not deleted:
            raise CommandError(f"no token {options['token_id']}")
        self.stdout.write(f"revoked {options['token_id']}")

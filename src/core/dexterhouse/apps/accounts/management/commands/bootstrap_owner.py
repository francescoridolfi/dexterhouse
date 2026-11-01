# SPDX-License-Identifier: AGPL-3.0-or-later
"""`manage.py bootstrap_owner --username admin` (password from `DH_OWNER_PASSWORD`).

Creates the default organization if needed and a user that owns it, so the first login to
the SPA works on a fresh install. Idempotent: an existing user keeps its password unless
`--reset-password` is given.
"""

import os

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError, CommandParser

from dexterhouse.apps.accounts.models import Membership, Organization, Role, User


class Command(BaseCommand):
    help = "Create the default organization and its first owner."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--username", default="admin")
        parser.add_argument("--email", default="")
        parser.add_argument("--password-env", default="DH_OWNER_PASSWORD")
        parser.add_argument("--reset-password", action="store_true")

    def handle(self, *args: object, **options: object) -> None:
        password = os.environ.get(str(options["password_env"]), "")
        org, _ = Organization.objects.get_or_create(
            slug=settings.DEFAULT_ORG_SLUG, defaults={"name": "Default"}
        )
        user = User.objects.filter(username=options["username"]).first()
        if user is None or options["reset_password"]:
            if not password:
                raise CommandError(f"set {options['password_env']} to the owner's password")
            if user is None:
                user = User.objects.create_user(
                    username=str(options["username"]), email=str(options["email"])
                )
            user.set_password(password)
            user.save()
        Membership.objects.update_or_create(
            user=user, organization=org, defaults={"role": Role.OWNER}
        )
        self.stdout.write(f"{user.get_username()} owns {org.slug}")

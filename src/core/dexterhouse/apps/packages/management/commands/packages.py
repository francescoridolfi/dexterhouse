# SPDX-License-Identifier: AGPL-3.0-or-later
"""`manage.py packages sync-builtin` (compose `migrate` service) and `check-compat`."""

from argparse import ArgumentParser
from typing import Any

from django.core.management.base import BaseCommand, CommandError

from dexterhouse.apps.packages.services import lifecycle
from dexterhouse.apps.packages.services.builtin import sync_builtin


class Command(BaseCommand):
    help = "Install the built-in packages and disable packages incompatible with this core."

    def add_arguments(self, parser: ArgumentParser) -> None:
        sub = parser.add_subparsers(dest="action", required=True)
        sub.add_parser(
            "sync-builtin",
            help="Install new or changed built-in packages, then run check-compat.",
        )
        sub.add_parser(
            "check-compat", help="Disable packages whose compat.core excludes this core."
        )

    def handle(self, *args: Any, **options: Any) -> None:
        if options["action"] == "sync-builtin":
            result = sync_builtin()
            self.stdout.write(
                f"built-in packages: {len(result.installed)} installed, "
                f"{len(result.unchanged)} unchanged, {len(result.removed)} removed"
            )
            for name, errors in result.rejected.items():
                self.stderr.write(f"{name}: rejected: {'; '.join(errors)}")
        for package in lifecycle.check_compat():
            self.stderr.write(f"warning: {package.name} disabled: incompatible with this core")
        if options["action"] == "sync-builtin" and result.rejected:
            raise CommandError(f"{len(result.rejected)} built-in package(s) are invalid")

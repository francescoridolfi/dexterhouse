# SPDX-License-Identifier: AGPL-3.0-or-later
"""`django-admin` with DexterHouse settings (console script `dexterhouse-manage`)."""

import os
import sys


def main() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "dexterhouse.settings.dev")
    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)

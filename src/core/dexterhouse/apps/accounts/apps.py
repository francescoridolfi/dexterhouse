# SPDX-License-Identifier: AGPL-3.0-or-later
from django.apps import AppConfig


class AccountsConfig(AppConfig):
    name = "dexterhouse.apps.accounts"
    label = "accounts"
    verbose_name = "Accounts"

    def ready(self) -> None:
        from dexterhouse.apps.accounts import schema  # noqa: F401  (registers the OpenAPI scheme)

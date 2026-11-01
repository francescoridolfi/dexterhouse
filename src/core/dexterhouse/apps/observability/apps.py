# SPDX-License-Identifier: AGPL-3.0-or-later
from django.apps import AppConfig


class ObservabilityConfig(AppConfig):
    name = "dexterhouse.apps.observability"
    label = "observability"
    verbose_name = "Observability"

    def ready(self) -> None:
        from dexterhouse.apps.observability import log, tracing

        tracing.configure()
        log.connect_celery()

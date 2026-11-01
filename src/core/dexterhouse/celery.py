# SPDX-License-Identifier: AGPL-3.0-or-later
"""Celery application: tasks only load IDs and call services (coding standards)."""

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "dexterhouse.settings.dev")

app = Celery("dexterhouse")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

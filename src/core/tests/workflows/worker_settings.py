# SPDX-License-Identifier: AGPL-3.0-or-later
"""Settings of the real Celery worker started by `test_recovery.py` (not used by pytest)."""

import os

from dexterhouse.settings.test import *  # noqa: F403  (settings pattern: re-export test)
from dexterhouse.settings.test import DATABASES

CELERY_TASK_ALWAYS_EAGER = False
CELERY_BROKER_URL = os.environ["DH_TEST_BROKER_URL"]
CELERY_WORKER_HIJACK_ROOT_LOGGER = False
DATABASES["default"]["NAME"] = os.environ["DH_TEST_DB_NAME"]
WORKFLOWS_FAKE_RUNNER = {"ask_questions": False, "tasks": 2, "delay_s": 0.25}
WORKFLOWS_STEP_LEASE_S = 2

# SPDX-License-Identifier: AGPL-3.0-or-later
"""Settings of the real Celery worker started by `test_recovery.py` (not used by pytest).

The built-in MCP servers a turn starts inherit `DJANGO_SETTINGS_MODULE` and `DATABASE_URL`
but not the `DH_TEST_*` variables, so those are optional here.
"""

import os
from pathlib import Path

from dexterhouse.settings.test import *  # noqa: F403  (settings pattern: re-export test)
from dexterhouse.settings.test import DATABASES

TEAM_PACKAGES = Path(__file__).parents[1] / "fixtures" / "agent_packages"

CELERY_TASK_ALWAYS_EAGER = False
CELERY_BROKER_URL = os.environ.get("DH_TEST_BROKER_URL", "memory://")
CELERY_WORKER_HIJACK_ROOT_LOGGER = False
if "DH_TEST_DB_NAME" in os.environ:
    DATABASES["default"]["NAME"] = os.environ["DH_TEST_DB_NAME"]
WORKFLOWS_FAKE_RUNNER = {"ask_questions": False, "tasks": 2, "delay_s": 0.25}
WORKFLOWS_STEP_LEASE_S = 2
if os.environ.get("DH_TEST_TURN_RUNNER") == "agents":
    WORKFLOWS_TURN_RUNNER = "dexterhouse.apps.workflows.runners.agents.AgentsTurnRunner"
    GATEWAY_FAKE_RESPONDER = "tests.workflows.agents_runtime.respond"
    AGENTS_PACKAGE_DIRS = [str(TEAM_PACKAGES)]

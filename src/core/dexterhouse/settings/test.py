# SPDX-License-Identifier: AGPL-3.0-or-later
"""Test settings: real Postgres and Redis (CI services), eager Celery."""

import json
import os
import tempfile
from pathlib import Path

from dexterhouse.settings.base import *  # noqa: F403  (settings pattern: re-export base)
from dexterhouse.settings.base import DATABASES, ENV, MIDDLEWARE

# nosec B105 below: test-only key, never used outside pytest.
SECRET_KEY = "test-key"  # noqa: S105 # nosec B105 # pragma: allowlist secret
DEBUG = False
ALLOWED_HOSTS = ["*"]
REDIS_URL = ENV.REDIS_URL
CELERY_BROKER_URL = "memory://"
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
MIDDLEWARE = [m for m in MIDDLEWARE if not m.startswith("whitenoise")]
# Async consumers use DB connections from worker threads; do not keep them open.
DATABASES["default"]["CONN_MAX_AGE"] = 0
# Throwaway Fernet key for encrypted columns in tests.
FERNET_KEY = "dGVzdC1mZXJuZXQta2V5LW5vdC1hLXNlY3JldC0wMDA="  # pragma: allowlist secret
GATEWAY_RETRY_DELAYS = (0.0, 0.0, 0.0)
# Installed packages of this test run (removed by the session fixture in tests/conftest.py).
# The tool server processes an end-to-end test starts get the test's store and registry from
# the `DH_TEST_*` variables (`tests/workflows/test_e2e_recruiter.py`); a plain run never sets them.
PACKAGES_DIR = Path(
    os.environ.get("DH_TEST_PACKAGES_DIR") or tempfile.mkdtemp(prefix="dh-test-packages-")
).resolve()
REGISTRY_INDEX_URL = os.environ.get("DH_TEST_REGISTRY_INDEX_URL", "")
MARKETPLACE_URL = ""
PACKAGES_GIT_MIRRORS = json.loads(os.environ.get("DH_TEST_PACKAGES_GIT_MIRRORS") or "{}")
MARKETPLACE_RAW_URL = os.environ.get("DH_TEST_MARKETPLACE_RAW_URL", "")
PACKAGES_ALLOW_LOCAL = True
# Engine tests script their turns; end-to-end tests opt in to AgentsTurnRunner (the default).
WORKFLOWS_TURN_RUNNER = "dexterhouse.apps.workflows.runners.fake.FakeTurnRunner"
GATEWAY_FAKE_RESPONDER = ""
# No runner in the unit tests: system actions succeed without executing anything.
RUNNER_CLIENT = "dexterhouse.apps.workspaces.client.LocalRunnerClient"
RUNNER_KEY = "test-runner-key"  # pragma: allowlist secret
# Rate limits off by default; the throttling tests switch them on with the `settings` fixture.
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
API_THROTTLE_RATES = {"client": None, "anon": None, "login": None}

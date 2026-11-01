# SPDX-License-Identifier: AGPL-3.0-or-later
"""Test settings: real Postgres and Redis (CI services), eager Celery."""

from dexterhouse.settings.base import *  # noqa: F403  (settings pattern: re-export base)
from dexterhouse.settings.base import ENV, MIDDLEWARE

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

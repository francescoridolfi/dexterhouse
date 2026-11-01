# SPDX-License-Identifier: AGPL-3.0-or-later
"""Local development settings."""

from dexterhouse.settings.base import *  # noqa: F403  (settings pattern: re-export base)
from dexterhouse.settings.base import ENV

DEBUG = True
ALLOWED_HOSTS = ["*"]
# nosec B105 below: dev-only fallback when no key is configured, prod refuses to start without one.
SECRET_KEY = ENV.secret_key() or "dev-insecure-key"  # nosec B105

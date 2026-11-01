# SPDX-License-Identifier: AGPL-3.0-or-later
"""Production settings: refuse to start without a secret key."""

from django.core.exceptions import ImproperlyConfigured

from dexterhouse.settings.base import *  # noqa: F403  (settings pattern: re-export base)
from dexterhouse.settings.base import SECRET_KEY

if not SECRET_KEY:
    raise ImproperlyConfigured("SECRET_KEY or SECRET_KEY_FILE must be set")

DEBUG = False
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_CONTENT_TYPE_NOSNIFF = True

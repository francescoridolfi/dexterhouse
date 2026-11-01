# SPDX-License-Identifier: AGPL-3.0-or-later
"""Fernet encryption for secret columns (`bytea`), key from `FERNET_KEY[_FILE]`."""

from cryptography.fernet import Fernet
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


def _fernet() -> Fernet:
    key = settings.FERNET_KEY
    if not key:
        raise ImproperlyConfigured("FERNET_KEY (or FERNET_KEY_FILE) is required to store secrets")
    return Fernet(key.encode("ascii"))


def encrypt(plaintext: str) -> bytes:
    return _fernet().encrypt(plaintext.encode("utf-8"))


def decrypt(token: bytes | memoryview) -> str:
    return _fernet().decrypt(bytes(token)).decode("utf-8")

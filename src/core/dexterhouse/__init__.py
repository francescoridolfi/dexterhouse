# SPDX-License-Identifier: AGPL-3.0-or-later
"""DexterHouse core package."""

from dexterhouse.celery import app as celery_app

__version__ = "0.1.0"
__all__ = ["__version__", "celery_app"]

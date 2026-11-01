# SPDX-License-Identifier: AGPL-3.0-or-later
"""Settings shared by every environment."""

from pathlib import Path

import dj_database_url
from celery.schedules import crontab

from dexterhouse.settings.env import get_env

ENV = get_env()
BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = ENV.secret_key()
DEBUG = ENV.DEBUG
ALLOWED_HOSTS = ENV.split(ENV.ALLOWED_HOSTS)
CSRF_TRUSTED_ORIGINS = ENV.split(ENV.CSRF_TRUSTED_ORIGINS)

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
    "rest_framework",
    "channels",
    "django_celery_beat",
    "dexterhouse.apps.accounts",
    "dexterhouse.apps.events",
    "dexterhouse.apps.gateway",
    "dexterhouse.apps.projects",
    "dexterhouse.apps.workflows",
    "dexterhouse.apps.memory",
    "dexterhouse.apps.agents",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "dexterhouse.urls"
ASGI_APPLICATION = "dexterhouse.asgi.application"
WSGI_APPLICATION = "dexterhouse.wsgi.application"
AUTH_USER_MODEL = "accounts.User"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

DATABASES = {"default": dj_database_url.parse(ENV.database_url(), conn_max_age=60)}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = ENV.DEFAULT_LANGUAGE
TIME_ZONE = ENV.TZ
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = Path(ENV.STATIC_ROOT) if ENV.STATIC_ROOT else BASE_DIR.parent / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
        "dexterhouse.apps.accounts.authentication.ApiTokenAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
}

REDIS_URL = ENV.REDIS_URL
CELERY_BROKER_URL = ENV.REDIS_URL
CELERY_RESULT_BACKEND = None
CELERY_TASK_DEFAULT_QUEUE = "default"
CELERY_TASK_ACKS_LATE = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TIMEZONE = TIME_ZONE
CELERY_BEAT_SCHEDULE = {
    "events-republish-pending": {
        "task": "dexterhouse.apps.events.tasks.republish_pending",
        "schedule": 30.0,
    },
    "events-maintain-partitions": {
        "task": "dexterhouse.apps.events.tasks.maintain_partitions",
        "schedule": crontab(minute=0, hour=3),
    },
}

DEFAULT_ORG_SLUG = ENV.DEFAULT_ORG_SLUG
EVENTS_RETENTION_MONTHS = ENV.EVENTS_RETENTION_MONTHS
EVENTS_STREAM_MAXLEN = 10_000
PRICES_FILE = ENV.PRICES_FILE
FX_EUR_PER_USD = ENV.FX_EUR_PER_USD
FERNET_KEY = ENV.fernet_key()
BUILTIN_DIR = Path(ENV.BUILTIN_DIR) if ENV.BUILTIN_DIR else BASE_DIR.parent.parent / "builtin"
WORKFLOWS_TURN_RUNNER = "dexterhouse.apps.workflows.runners.fake.FakeTurnRunner"
WORKFLOWS_FAKE_RUNNER: dict[str, object] = {}  # FakeTurnRunner script, see runners/fake.py
WORKFLOWS_STEP_LEASE_S = 900
WORKFLOWS_STEP_MAX_ATTEMPTS = 3
WORKFLOWS_REPO_CHECKER = "dexterhouse.apps.projects.services.validation.git_ls_remote"
CELERY_BEAT_SCHEDULE["workflows-reconcile"] = {
    "task": "dexterhouse.apps.workflows.tasks.reconcile",
    "schedule": 60.0,
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": ENV.LOG_LEVEL},
}

# Agents runtime and LLM gateway (E-03)
CELERY_TASK_ROUTES = {"dexterhouse.apps.agents.tasks.*": {"queue": "agents"}}
GATEWAY_RETRY_DELAYS = (2.0, 4.0, 8.0)
AGENTS_TOOL_PACKAGE_DIRS = ["/data/packages/tools"]

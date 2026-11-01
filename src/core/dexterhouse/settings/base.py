# SPDX-License-Identifier: AGPL-3.0-or-later
"""Settings shared by every environment."""

from pathlib import Path

import dj_database_url
from celery.schedules import crontab

from dexterhouse.apps.observability.log import logging_config
from dexterhouse.settings.env import get_env, read_secret_file

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
    "dexterhouse.apps.observability",
    "dexterhouse.apps.notifications",
    "dexterhouse.apps.workspaces",
    "dexterhouse.apps.packages",
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
    "dexterhouse.apps.observability.middleware.RequestContextMiddleware",
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
# Runner results (E-05) come back through Redis; the core's own tasks store none.
CELERY_RESULT_BACKEND = ENV.REDIS_URL
CELERY_TASK_IGNORE_RESULT = True
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
WORKFLOWS_TURN_RUNNER = "dexterhouse.apps.workflows.runners.agents.AgentsTurnRunner"
WORKFLOWS_FAKE_RUNNER: dict[str, object] = {}  # FakeTurnRunner script, see runners/fake.py
WORKFLOWS_STEP_LEASE_S = 900
WORKFLOWS_STEP_MAX_ATTEMPTS = 3
WORKFLOWS_REPO_CHECKER = "dexterhouse.apps.projects.services.validation.git_ls_remote"
CELERY_BEAT_SCHEDULE["observability-rollup-llm-calls"] = {
    "task": "dexterhouse.apps.observability.tasks.rollup_llm_calls",
    "schedule": crontab(minute=30, hour=3, day_of_month=1),
}
CELERY_BEAT_SCHEDULE["workflows-reconcile"] = {
    "task": "dexterhouse.apps.workflows.tasks.reconcile",
    "schedule": 60.0,
}
# Human in the loop (E-06): gate reminders after the organization's TTL, optional email.
CELERY_BEAT_SCHEDULE["workflows-remind-gates"] = {
    "task": "dexterhouse.apps.workflows.tasks.remind_gates",
    "schedule": 300.0,
}
EMAIL_HOST = ENV.EMAIL_HOST
EMAIL_PORT = ENV.EMAIL_PORT
EMAIL_HOST_USER = ENV.EMAIL_HOST_USER
EMAIL_HOST_PASSWORD = read_secret_file(ENV.EMAIL_HOST_PASSWORD_FILE)
EMAIL_USE_TLS = ENV.EMAIL_USE_TLS
DEFAULT_FROM_EMAIL = ENV.DEFAULT_FROM_EMAIL
NOTIFICATIONS_EMAIL_ENABLED = ENV.NOTIFICATIONS_EMAIL
NOTIFICATIONS_PUBLIC_URL = ENV.PUBLIC_URL

# JSON logs with trace/project/turn context (F-012); LOG_FORMAT=console for local dev.
LOGGING = logging_config(ENV.LOG_LEVEL, ENV.LOG_FORMAT)
CELERY_WORKER_HIJACK_ROOT_LOGGER = False  # workers log through LOGGING too

# Agents runtime and LLM gateway (E-03)
# `run_step` runs the agent turn synchronously (AgentsTurnRunner): it belongs on `agents`.
CELERY_TASK_ROUTES = {
    "dexterhouse.apps.agents.tasks.*": {"queue": "agents"},
    "dexterhouse.apps.workflows.tasks.run_step": {"queue": "agents"},
}
GATEWAY_RETRY_DELAYS = (2.0, 4.0, 8.0)
# Dotted path answering the `fake` provider (tests, demos without LLM):
# `dexterhouse.apps.agents.demo.respond`, scripted by AGENTS_DEMO_SCRIPT (agents/demo).
GATEWAY_FAKE_RESPONDER = ENV.GATEWAY_FAKE_RESPONDER
AGENTS_DEMO_SCRIPT: dict[str, object] = {}
AGENTS_TOOL_PACKAGE_DIRS = ["/data/packages/tools"]
# Agent packages by lookup order: built-in team (E-04), then installed packages (E-07).
AGENTS_PACKAGE_DIRS = [str(BUILTIN_DIR / "agents"), "/data/packages/agents"]

# Runner and workspaces (E-05): the runner client, the runner key for grants, limits.
RUNNER_CLIENT = "dexterhouse.apps.workspaces.client.CeleryRunnerClient"
RUNNER_KEY = ENV.runner_key()
WORKSPACE_LIMITS = {
    "cpus": ENV.WORKSPACE_CPUS,
    "memory": ENV.WORKSPACE_MEM,
    "disk": ENV.WORKSPACE_DISK,
}
WORKSPACE_IDLE_AFTER_S = 15 * 60
WORKSPACE_IDLE_DESTROY_H = ENV.WORKSPACE_IDLE_DESTROY_H
CELERY_TASK_ROUTES["core.runner.*"] = {"queue": "core-callbacks"}
CELERY_BEAT_SCHEDULE["workspaces-cleanup"] = {
    "task": "dexterhouse.apps.workspaces.tasks.cleanup",
    "schedule": 600.0,
}

# Packages (E-07): agents, tools and processes are read from the installed PackageVersions;
# built-ins are synced by `manage.py packages sync-builtin`, the others stored in PACKAGES_DIR.
PACKAGES_DIR = Path(ENV.PACKAGES_DIR)
REGISTRY_INDEX_URL = ENV.REGISTRY_INDEX_URL
REGISTRY_INDEX_TTL_S = 300
PACKAGES_ALLOW_LOCAL = ENV.PACKAGES_ALLOW_LOCAL  # local paths and git+file:// (development)
CELERY_BEAT_SCHEDULE["packages-collect-unused"] = {
    "task": "dexterhouse.apps.packages.tasks.collect_unused",
    "schedule": 3600.0,
}
CELERY_BEAT_SCHEDULE["packages-check-updates"] = {
    "task": "dexterhouse.apps.packages.tasks.check_updates",
    "schedule": crontab(minute=30, hour=4),
}

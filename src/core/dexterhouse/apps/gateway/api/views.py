# SPDX-License-Identifier: AGPL-3.0-or-later
"""REST v1: model profiles, providers and the price table (admin.md).

Keys are never stored nor returned: a profile names the environment variable holding it
(`api_key_env`) and the API only says whether that variable is set.
"""

import os
import shutil
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from rest_framework import serializers
from rest_framework.request import Request
from rest_framework.response import Response

from dexterhouse.apps.accounts.models import Role, Scope
from dexterhouse.apps.gateway.models import ModelProfile, ProfileChoice, ProviderChoice
from dexterhouse.apps.gateway.pricing import get_prices
from dexterhouse.apps.gateway.providers import LOCAL_PROVIDERS, PROVIDERS
from dexterhouse.apps.gateway.services.profiles import DEFAULT_KEY_ENV, resolve_profile
from dexterhouse.common.api import ApiView
from dexterhouse.common.errors import ValidationFailedError

READ = (Role.VIEWER, Scope.PROJECTS_READ)
ADMIN = (Role.ADMIN, Scope.PROJECTS_WRITE)
SECRET_SET = "***set***"  # noqa: S105  # nosec B105: placeholder, not a secret
NEEDS_KEY = frozenset(DEFAULT_KEY_ENV)


def _key_state(provider: str, env_name: str) -> str | None:
    name = env_name or DEFAULT_KEY_ENV.get(provider, "")
    if not name:
        return None
    return SECRET_SET if os.environ.get(name) else None


def profile_json(organization_id: Any, profile: str) -> dict[str, Any]:
    resolved = resolve_profile(organization_id, None, profile) if profile != "embed" else None
    row = ModelProfile.objects.filter(
        organization_id=organization_id, project__isnull=True, profile=profile
    ).first()
    provider = row.provider if row else (resolved.provider if resolved else None)
    model = row.model if row else (resolved.model if resolved else None)
    env_name = row.api_key_env if row else ""
    return {
        "profile": profile,
        "configured": row is not None,
        "source": "organization" if row else ("default" if resolved else None),
        "provider": provider,
        "model": model,
        "base_url": row.base_url if row else "",
        "api_key_env": env_name or (DEFAULT_KEY_ENV.get(provider or "", "") or None),
        "api_key": _key_state(provider or "", env_name) if provider else None,
        "needs_key": provider in NEEDS_KEY,
        "is_local": bool(row.is_local) if row else provider in LOCAL_PROVIDERS,
        "options": row.options if row else {},
    }


class ProfileInput(serializers.Serializer):
    provider = serializers.ChoiceField(choices=ProviderChoice.values)
    model = serializers.CharField(max_length=120)
    base_url = serializers.CharField(max_length=300, required=False, allow_blank=True, default="")
    api_key_env = serializers.RegexField(
        r"^[A-Z][A-Z0-9_]{0,63}$", required=False, allow_blank=True, default=""
    )
    options = serializers.DictField(required=False, default=dict)
    is_local = serializers.BooleanField(required=False, default=False)


class ModelProfilesView(ApiView):
    def get(self, request: Request) -> Response:
        ctx = self.require(*READ)
        return Response({"results": [profile_json(ctx.organization.id, p) for p in ProfileChoice]})


class ModelProfileView(ApiView):
    def put(self, request: Request, profile: str) -> Response:
        ctx = self.require(*ADMIN)
        if profile not in ProfileChoice.values:
            raise ValidationFailedError(
                "unknown profile", [{"field": "profile", "message": "strong|balanced|fast|embed"}]
            )
        body = ProfileInput(data=request.data)
        body.is_valid(raise_exception=True)
        with transaction.atomic():
            row = ModelProfile.objects.filter(
                organization=ctx.organization, project__isnull=True, profile=profile
            ).first() or ModelProfile(organization=ctx.organization, profile=profile)
            for name, value in body.validated_data.items():
                setattr(row, name, value)
            try:
                row.save()
            except ValidationError as exc:
                raise ValidationFailedError(
                    "invalid model profile",
                    [{"field": "options", "message": m} for m in exc.messages],
                ) from None
        return Response(profile_json(ctx.organization.id, profile))


class ProvidersView(ApiView):
    def get(self, request: Request) -> Response:
        self.require(*READ)
        rows = []
        for name in PROVIDERS:
            entry: dict[str, Any] = {
                "id": name,
                "local": name in LOCAL_PROVIDERS,
                "needs_key": name in NEEDS_KEY,
                "key_set": _key_state(name, "") is not None,
            }
            if name == "anthropic-cli":
                entry["binary_found"] = shutil.which("claude") is not None
            if name == "ollama":
                entry["base_url"] = os.environ.get("OLLAMA_BASE_URL", "")
            rows.append(entry)
        return Response({"results": rows})


class PricingView(ApiView):
    def get(self, request: Request) -> Response:
        self.require(*READ)
        table = get_prices()
        return Response(
            {
                "price_version": table.price_version,
                "currency": table.currency,
                "eur_per_usd": str(table.eur_per_usd),
                "models": {
                    provider: {
                        model: price.model_dump(mode="json", exclude_none=True)
                        for model, price in models.items()
                    }
                    for provider, models in table.models.items()
                },
            }
        )

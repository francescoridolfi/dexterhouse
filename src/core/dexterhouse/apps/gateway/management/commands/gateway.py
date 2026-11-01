# SPDX-License-Identifier: AGPL-3.0-or-later
"""`manage.py gateway call "<prompt>"`: one completion through a provider, for debugging."""

import uuid
from argparse import ArgumentParser
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from dexterhouse.apps.accounts.models import Organization
from dexterhouse.apps.gateway.messages import CompletionRequest, Message, TextPart
from dexterhouse.apps.gateway.providers import UnknownProviderError, get_provider
from dexterhouse.apps.gateway.services.complete import complete


class Command(BaseCommand):
    help = "Send one prompt through an LLM provider and record the LLMCall."

    def add_arguments(self, parser: ArgumentParser) -> None:
        sub = parser.add_subparsers(dest="action", required=True)
        call = sub.add_parser("call")
        call.add_argument("prompt")
        call.add_argument("--provider", default="fake")
        call.add_argument("--model", default="fake-model")
        call.add_argument("--profile", default="fast")
        call.add_argument("--project", type=uuid.UUID, default=None)
        call.add_argument("--org", default=settings.DEFAULT_ORG_SLUG)

    def handle(self, *args: Any, **options: Any) -> None:
        organization = Organization.objects.filter(slug=options["org"]).first()
        if organization is None:
            raise CommandError(f"unknown organization {options['org']}")
        try:
            provider = get_provider(options["provider"])
        except UnknownProviderError as exc:
            raise CommandError(f"unknown provider {exc}") from exc
        request = CompletionRequest(
            messages=[Message(role="user", parts=[TextPart(text=options["prompt"])])],
            profile=options["profile"],
            model=options["model"],
            max_tokens=1024,
        )
        result, call = complete(
            request,
            provider=provider,
            organization_id=organization.id,
            project_id=options["project"] or uuid.uuid4(),
        )
        self.stdout.write(result.message.text())
        self.stdout.write(
            f"llm_call={call.id} tokens={call.input_tokens}/{call.output_tokens} "
            f"cost={call.cost} EUR price_version={call.price_version}"
        )

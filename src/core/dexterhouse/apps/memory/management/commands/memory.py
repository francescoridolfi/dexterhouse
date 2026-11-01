# SPDX-License-Identifier: AGPL-3.0-or-later
"""`manage.py memory reindex [--project <id> | --all] [--embedder p/m] [--batch 64] [--dry-run]`."""

import uuid
from argparse import ArgumentParser
from typing import Any

from django.core.management.base import BaseCommand, CommandError

from dexterhouse.apps.accounts.models import Organization
from dexterhouse.apps.gateway.embeddings import build_embedder, resolve_embedder
from dexterhouse.apps.gateway.services.profiles import ResolvedProfile
from dexterhouse.apps.memory.models import MemoryChunk
from dexterhouse.apps.memory.services.reindex import reindex_project


class Command(BaseCommand):
    help = "Re-embed project memory with the current (or given) embedder."

    def add_arguments(self, parser: ArgumentParser) -> None:
        sub = parser.add_subparsers(dest="action", required=True)
        reindex = sub.add_parser("reindex")
        scope = reindex.add_mutually_exclusive_group(required=True)
        scope.add_argument("--project", type=uuid.UUID)
        scope.add_argument("--all", action="store_true")
        reindex.add_argument("--embedder", help="provider/model, e.g. ollama/mxbai-embed-large")
        reindex.add_argument("--org", help="organization slug used to resolve the embed profile")
        reindex.add_argument("--batch", type=int, default=64)
        reindex.add_argument("--dry-run", action="store_true")

    def handle(self, *args: Any, **options: Any) -> None:
        projects = (
            [options["project"]]
            if options["project"]
            else list(MemoryChunk.objects.values_list("project_id", flat=True).distinct())
        )
        embedder = self._embedder(options)
        for project_id in projects:
            result = reindex_project(
                project_id, embedder, batch=options["batch"], dry_run=options["dry_run"]
            )
            verb = "would re-embed" if options["dry_run"] else "re-embedded"
            self.stdout.write(f"{project_id}: {verb} {result.chunks} chunks with {embedder.name}")

    def _embedder(self, options: dict[str, Any]) -> Any:
        if options["embedder"]:
            provider, _, model = options["embedder"].partition("/")
            if not model:
                raise CommandError("--embedder must be provider/model")
            return build_embedder(ResolvedProfile(profile="embed", provider=provider, model=model))
        org = (
            Organization.objects.filter(slug=options["org"]).first()
            if options["org"]
            else Organization.objects.first()
        )
        if org is None:
            raise CommandError("no organization")
        return resolve_embedder(org.id)

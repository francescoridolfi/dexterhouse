# SPDX-License-Identifier: AGPL-3.0-or-later
"""`manage.py events tail <project_id>` and `manage.py events emit <project_id> <type>`."""

import json
import time
import uuid
from argparse import ArgumentParser
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from pydantic import ValidationError

from dexterhouse.apps.accounts.models import Organization
from dexterhouse.apps.events.schemas import Actor, EventEnvelope, UnknownEventTypeError
from dexterhouse.apps.events.services import publisher, streams


class Command(BaseCommand):
    help = "Inspect the event bus: follow a project stream or emit an event."

    def add_arguments(self, parser: ArgumentParser) -> None:
        sub = parser.add_subparsers(dest="action", required=True)
        tail = sub.add_parser("tail", help="Follow a project's Redis stream.")
        tail.add_argument("project_id", type=uuid.UUID)
        tail.add_argument("--from-start", action="store_true", help="Replay the whole stream.")
        tail.add_argument("--count", type=int, default=0, help="Stop after N events.")
        tail.add_argument("--timeout", type=float, default=0, help="Stop after S seconds idle.")
        tail.add_argument("--json", action="store_true", help="Print raw envelopes.")
        emit = sub.add_parser("emit", help="Emit an event (system actor), for debugging.")
        emit.add_argument("project_id", type=uuid.UUID)
        emit.add_argument("type")
        emit.add_argument("--payload", default="{}", help="JSON payload.")
        emit.add_argument("--org", default=settings.DEFAULT_ORG_SLUG, help="Organization slug.")

    def handle(self, *args: Any, **options: Any) -> None:
        if options["action"] == "tail":
            self._tail(**options)
        else:
            self._emit(**options)

    def _tail(self, project_id: uuid.UUID, **options: Any) -> None:
        last_id = "0-0" if options["from_start"] else "$"
        printed = 0
        idle_since = time.monotonic()
        while True:
            entries = streams.read_after(project_id, last_id, block_ms=1_000)
            for entry_id, envelope in entries:
                last_id = entry_id
                self.stdout.write(self._format(envelope, raw=options["json"]))
                printed += 1
                if options["count"] and printed >= options["count"]:
                    return
            if entries:
                idle_since = time.monotonic()
            elif options["timeout"] and time.monotonic() - idle_since >= options["timeout"]:
                return

    @staticmethod
    def _format(envelope: EventEnvelope, *, raw: bool) -> str:
        if raw:
            return envelope.model_dump_json()
        actor = envelope.actor.name or envelope.actor.type
        payload = json.dumps(envelope.payload, separators=(",", ":"), default=str)
        return f"{envelope.created_at.isoformat()} {envelope.type} [{actor}] {payload}"

    def _emit(self, project_id: uuid.UUID, **options: Any) -> None:
        organization = Organization.objects.filter(slug=options["org"]).first()
        if organization is None:
            raise CommandError(f"unknown organization {options['org']}")
        try:
            envelope = publisher.emit(
                options["type"],
                organization_id=organization.id,
                project_id=project_id,
                actor=Actor(type="system", name="cli"),
                payload=json.loads(options["payload"]),
            )
        except (UnknownEventTypeError, ValidationError, ValueError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(str(envelope.id))

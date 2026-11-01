# SPDX-License-Identifier: AGPL-3.0-or-later
"""Gate TTL (state_machines/gate.md): an open gate past `expires_at` is never decided by the
system; the deciders are notified again and the TTL starts over (`gate.renotified`)."""

from datetime import datetime

from django.db import transaction
from django.utils import timezone

from dexterhouse.apps.projects.services.actors import emit
from dexterhouse.apps.workflows.engine import common
from dexterhouse.apps.workflows.models import Gate, GateStatus


def remind_gates(now: datetime | None = None) -> int:
    """Beat: remind every open gate whose TTL elapsed; returns how many were reminded."""
    now = now or timezone.now()
    due = Gate.objects.filter(status=GateStatus.OPEN, expires_at__lte=now)
    count = 0
    for gate_id in due.values_list("pk", flat=True):
        with transaction.atomic():
            gate = (
                Gate.objects.select_for_update(skip_locked=True, of=("self",))
                .select_related("project__organization", "phase_run")
                .filter(pk=gate_id, status=GateStatus.OPEN, expires_at__lte=now)
                .first()
            )
            if gate is None:
                continue
            _remind(gate, now)
        count += 1
    return count


def _remind(gate: Gate, now: datetime) -> None:
    project = gate.project
    if gate.reminders == 0:
        emit(project, "gate.expired", {"gate_id": gate.id}, correlation_id=gate.id)
    ttl = common.gate_ttl(project)
    gate.reminders += 1
    gate.expires_at = now + ttl if ttl else None
    gate.notified_at = now
    common.save(gate, "reminders", "expires_at", "notified_at")
    emit(
        project,
        "gate.renotified",
        {"gate_id": gate.id, "times": gate.reminders},
        correlation_id=gate.id,
    )
    common.notify_gate(gate, reminder=gate.reminders)

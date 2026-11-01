# SPDX-License-Identifier: AGPL-3.0-or-later
"""Notify the people who can act on a gate: in app (record + `notification.created`) and,
when `NOTIFICATIONS_EMAIL_ENABLED`, by email through the Django mail backend."""

import uuid
from typing import Any

import structlog
from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import QuerySet
from django.utils import timezone

from dexterhouse.apps.accounts.models import Membership, Role, User
from dexterhouse.apps.notifications.models import Notification, NotificationKind
from dexterhouse.apps.projects.services.actors import emit

logger = structlog.get_logger(__name__)

#: Who may act on each gate type (contracts/api/workflow.md, ux_2d_flows.md F2/F3/F8).
DECIDERS = {
    "approval": (Role.OWNER, Role.ADMIN),
    "escalation": (Role.OWNER, Role.ADMIN),
    "question": (Role.OWNER, Role.ADMIN, Role.MEMBER),
}


def recipients(gate: Any) -> QuerySet[User]:
    roles = DECIDERS.get(gate.type, (Role.OWNER, Role.ADMIN))
    members = Membership.objects.filter(
        organization_id=gate.project.organization_id, role__in=roles
    )
    return User.objects.filter(
        pk__in=members.values_list("user_id", flat=True), is_active=True
    ).order_by("date_joined")


def notify_gate(gate: Any, *, reminder: int = 0) -> list[Notification]:
    """One notification per decider of an open gate; `reminder` > 0 for a TTL reminder."""
    project = gate.project
    payload = gate.payload or {}
    kind = NotificationKind.GATE_REMINDER if reminder else NotificationKind.GATE_OPENED
    title = str(payload.get("title") or gate.gate_id)
    if reminder:
        title = f"Reminder: {title}"
    body = f"{project.name}: {payload.get('summary') or ''}".strip()
    data = {
        "project_name": project.name,
        "phase_id": gate.phase_run.phase_id,
        "gate_type": gate.type,
        "times": reminder,
    }
    created = []
    for user in recipients(gate):
        note = Notification.objects.create(
            organization_id=project.organization_id,
            user=user,
            project=project,
            gate=gate,
            kind=kind,
            title=title[:200],
            body=body,
            data=data,
        )
        emit(
            project,
            "notification.created",
            {
                "notification_id": note.id,
                "user_id": user.id,
                "kind": kind,
                "title": note.title,
                "gate_id": gate.id,
                "gate_type": gate.type,
            },
            correlation_id=gate.id,
        )
        if settings.NOTIFICATIONS_EMAIL_ENABLED and user.email:
            transaction.on_commit(lambda nid=str(note.id): _send_later(nid))
        created.append(note)
    return created


def _send_later(notification_id: str) -> None:
    from dexterhouse.apps.notifications.tasks import send_email

    send_email.delay(notification_id)


def gate_closed(gate: Any) -> int:
    """A decided gate needs nobody anymore: its unread notifications are marked read."""
    return Notification.objects.filter(gate_id=gate.id, read_at__isnull=True).update(
        read_at=timezone.now(), updated_at=timezone.now()
    )


def send_email(notification_id: uuid.UUID) -> bool:
    """Send one notification by email (once); False when there is nothing to send."""
    note = (
        Notification.objects.select_related("user", "project")
        .filter(pk=notification_id, emailed_at__isnull=True)
        .first()
    )
    if note is None or not note.user.email:
        return False
    link = settings.NOTIFICATIONS_PUBLIC_URL.rstrip("/")
    if note.project_id:
        link += f"/projects/{note.project_id}"
        if note.gate_id:
            link += f"?gate={note.gate_id}"
    message = f"{note.body}\n\nOpen DexterHouse: {link}\n"
    send_mail(
        f"[DexterHouse] {note.title}",
        message,
        settings.DEFAULT_FROM_EMAIL,
        [note.user.email],
    )
    note.emailed_at = timezone.now()
    note.save(update_fields=["emailed_at", "updated_at"])
    logger.info("notifications.emailed", notification_id=str(note.id))
    return True


def for_user(user: User, organization_id: uuid.UUID) -> QuerySet[Notification]:
    return Notification.objects.filter(user=user, organization_id=organization_id)


def mark_read(user: User, organization_id: uuid.UUID, ids: list[uuid.UUID] | None = None) -> int:
    """Mark the user's notifications read (all unread ones when `ids` is None)."""
    rows = for_user(user, organization_id).filter(read_at__isnull=True)
    if ids is not None:
        rows = rows.filter(pk__in=ids)
    now = timezone.now()
    return rows.update(read_at=now, updated_at=now)

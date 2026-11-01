# SPDX-License-Identifier: AGPL-3.0-or-later
import uuid
from datetime import timedelta

import pytest
import redis
from django.db import DatabaseError, transaction
from django.utils import timezone
from pydantic import ValidationError

from dexterhouse.apps.events.models import Event
from dexterhouse.apps.events.schemas import Actor, UnknownEventTypeError
from dexterhouse.apps.events.services import publisher, streams
from dexterhouse.apps.events.tasks import republish_pending

pytestmark = pytest.mark.django_db


def emit_phase_ready(organization, project_id, system, **kwargs):
    return publisher.emit(
        "phase.ready",
        organization_id=organization.id,
        project_id=project_id,
        actor=system,
        payload={"phase_id": "analysis"},
        **kwargs,
    )


def test_emit_writes_postgres_then_redis(
    organization, project_id, system, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=True):
        envelope = emit_phase_ready(organization, project_id, system)
    row = Event.objects.get(id=envelope.id)
    assert row.published is True
    assert row.type == "phase.ready"
    assert row.correlation_id == envelope.id
    assert row.actor_name == "engine"
    assert str(row) == f"phase.ready {envelope.id}"
    entries = streams.read_after(project_id, "0-0")
    assert [env.id for _, env in entries] == [envelope.id]
    assert publisher.to_envelope(row) == envelope


def test_rollback_publishes_nothing(organization, project_id, system):
    def emit_then_fail():
        with transaction.atomic():
            emit_phase_ready(organization, project_id, system)
            raise RuntimeError("abort")

    with pytest.raises(RuntimeError):
        emit_then_fail()
    assert not Event.objects.exists()
    assert streams.read_after(project_id, "0-0") == []


def test_redis_down_leaves_outbox_then_sweep_publishes(
    organization, project_id, system, monkeypatch, django_capture_on_commit_callbacks
):
    def broken(envelope, client=None):
        raise redis.ConnectionError("down")

    monkeypatch.setattr(streams, "append", broken)
    with django_capture_on_commit_callbacks(execute=True):
        envelope = emit_phase_ready(organization, project_id, system)
    assert Event.objects.get(id=envelope.id).published is False
    assert publisher.republish_pending(now=timezone.now() + timedelta(minutes=1)) == 0
    monkeypatch.undo()
    assert publisher.republish_pending() == 0  # too recent: on_commit may still be running
    assert publisher.republish_pending(now=timezone.now() + timedelta(minutes=1)) == 1
    assert Event.objects.get(id=envelope.id).published is True
    assert republish_pending() == 0


def test_stream_only_event_skips_postgres(organization, project_id):
    publisher.emit(
        "agent.speaking",
        organization_id=organization.id,
        project_id=project_id,
        actor=Actor(type="agent", id=uuid.uuid4(), name="Analyst"),
        payload={
            "turn_id": str(uuid.uuid4()),
            "agent_id": str(uuid.uuid4()),
            "text": "hi",
            "seq": 1,
        },
    )
    assert not Event.objects.exists()
    [(_, envelope)] = streams.read_after(project_id, "0-0")
    assert envelope.payload["text"] == "hi"
    assert streams.latest_id(project_id) != "0-0"


def test_stream_only_event_survives_redis_down(organization, project_id, monkeypatch):
    monkeypatch.setattr(
        streams, "append", lambda *a, **k: (_ for _ in ()).throw(redis.RedisError())
    )
    publisher.emit(
        "agent.speaking",
        organization_id=organization.id,
        project_id=project_id,
        actor=Actor(type="agent"),
        payload={
            "turn_id": str(uuid.uuid4()),
            "agent_id": str(uuid.uuid4()),
            "text": "x",
            "seq": 2,
        },
    )


@pytest.mark.parametrize(
    ("event_type", "actor", "payload", "error"),
    [
        ("nope.nope", "system", {}, UnknownEventTypeError),
        ("project.paused", "system", {}, publisher.ActorNotAllowedError),
        ("phase.ready", "system", {"phase": "x"}, ValidationError),
    ],
)
def test_emit_rejects(organization, project_id, event_type, actor, payload, error):
    with pytest.raises(error):
        publisher.emit(
            event_type,
            organization_id=organization.id,
            project_id=project_id,
            actor=Actor(type=actor),
            payload=payload,
        )


def test_events_are_immutable(organization, project_id, system):
    envelope = emit_phase_ready(organization, project_id, system)
    events = Event.objects.filter(id=envelope.id)
    with pytest.raises(DatabaseError, match="append-only"), transaction.atomic():
        events.update(payload={"phase_id": "tampered"})
    with pytest.raises(DatabaseError, match="DELETE is not allowed"), transaction.atomic():
        events.delete()
    assert events.update(published=True) == 1
    assert events.get().payload == {"phase_id": "analysis"}


def test_latest_id_of_empty_stream(project_id):
    assert streams.latest_id(project_id) == "0-0"

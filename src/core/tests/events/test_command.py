# SPDX-License-Identifier: AGPL-3.0-or-later
import json
from io import StringIO

import pytest
from django.core.management import CommandError, call_command

pytestmark = pytest.mark.django_db(transaction=True)


def run(*args: str) -> str:
    out = StringIO()
    call_command("events", *args, stdout=out)
    return out.getvalue()


def test_emit_then_tail(organization, project_id):
    payload = json.dumps({"phase_id": "analysis"})
    event_id = run("emit", str(project_id), "phase.ready", "--payload", payload).strip()
    lines = run("tail", str(project_id), "--from-start", "--count", "1").splitlines()
    assert len(lines) == 1
    assert "phase.ready [cli]" in lines[0]
    raw = run("tail", str(project_id), "--from-start", "--count", "1", "--json")
    assert json.loads(raw)["id"] == event_id


def test_tail_stops_after_idle_timeout(project_id):
    assert run("tail", str(project_id), "--timeout", "0.1") == ""


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (["phase.ready", "--org", "missing"], "unknown organization"),
        (["phase.nope"], "phase.nope"),
        (["phase.ready", "--payload", "{}"], "phase_id"),
    ],
)
def test_emit_errors(organization, project_id, args, message):
    with pytest.raises(CommandError, match=message):
        run("emit", str(project_id), *args)

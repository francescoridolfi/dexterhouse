# SPDX-License-Identifier: AGPL-3.0-or-later
"""Read APIs used by the SPA: session auth, organization, events, team, profiles, meta."""

import pytest
from rest_framework.test import APIClient

from dexterhouse.apps.agents.models import AgentInstance, AgentTurn, ToolCall
from dexterhouse.apps.events.models import Event
from tests.workflows.conftest import drain

pytestmark = pytest.mark.django_db
PASSWORD = "pw-for-tests-only"  # the `user` fixture's  # pragma: allowlist secret


def test_session_login_flow_with_csrf(user):
    api = APIClient(enforce_csrf_checks=True)
    assert api.get("/api/v1/auth/me").status_code == 403
    response = api.get("/api/v1/auth/csrf")
    token = response.cookies["csrftoken"].value
    denied = api.post("/api/v1/auth/login", {"username": "ada", "password": "x"}, format="json")
    assert denied.status_code == 403  # no CSRF header
    bad = api.post(
        "/api/v1/auth/login", {"username": "ada", "password": "x"}, format="json",
        HTTP_X_CSRFTOKEN=token,
    )  # fmt: skip
    assert bad.status_code == 401
    ok = api.post(
        "/api/v1/auth/login", {"username": "ada", "password": PASSWORD},
        format="json", HTTP_X_CSRFTOKEN=token,
    )  # fmt: skip
    assert ok.status_code == 200
    assert ok.json()["organizations"] == [{"slug": "default", "name": "Default", "role": "owner"}]
    session = ok.cookies["sessionid"]
    assert session["httponly"]
    assert api.get("/api/v1/auth/me").json()["username"] == "ada"
    token = api.cookies["csrftoken"].value  # rotated at login
    assert api.post("/api/v1/auth/logout", HTTP_X_CSRFTOKEN=token).status_code == 204
    assert api.get("/api/v1/auth/me").status_code == 403


def test_organization_and_members(client, make_member):
    body = client.get("/api/v1/organization").json()
    assert (body["slug"], body["budget_monthly"]) == ("default", None)
    response = client.patch(
        "/api/v1/organization", {"name": "Acme", "settings": {"language": "it"}}, format="json"
    )
    assert response.json()["name"] == "Acme"
    assert response.json()["settings"] == {"language": "it"}
    bad = client.patch("/api/v1/organization", {"settings": {"evil": 1}}, format="json")
    assert bad.status_code == 400
    viewer = make_member("viewer")
    assert viewer.patch("/api/v1/organization", {"name": "x"}, format="json").status_code == 403
    members = client.get("/api/v1/organization/members").json()["results"]
    assert {m["role"] for m in members} == {"owner", "viewer"}


def test_events_list_filters_and_summary(client, started):
    project = started()
    drain(project)
    url = f"/api/v1/projects/{project.id}/events"
    page = client.get(url, {"limit": 3}).json()
    assert [e["type"] for e in page["results"]][:2] == ["project.created", "project.started"]
    assert page["next"]
    gates = client.get(url, {"types": "gate.opened,project.waiting"}).json()["results"]
    assert {e["type"] for e in gates} == {"gate.opened", "project.waiting"}
    assert client.get(url, {"actor": "user"}).json()["results"][0]["actor"]["type"] == "user"
    phase = client.get(url, {"phase": "analysis", "types": "phase.started"}).json()["results"]
    assert len(phase) == 1
    first = Event.objects.filter(project_id=project.id).order_by("created_at").first()
    later = client.get(url, {"from": first.created_at.isoformat(), "limit": 1000}).json()
    assert len(later["results"]) == Event.objects.filter(project_id=project.id).count()
    assert client.get(url, {"to": "yesterday"}).status_code == 400
    summary = client.get(f"{url}/summary").json()
    assert summary["by_type"]["project.created"] == 1
    single = client.get(f"/api/v1/events/{first.id}").json()
    assert single["type"] == "project.created"
    agent = AgentInstance.objects.filter(project=project).first()
    assert client.get(url, {"agent": str(agent.id)}).status_code == 200
    assert client.get(url, {"actor": str(agent.id)}).status_code == 200


def test_team_and_turns(client, started, organization):
    project = started()
    agent = AgentInstance.objects.get(project=project, role="analyst")
    turn = AgentTurn.objects.create(
        organization=organization, project=project, agent_instance=agent, purpose="analysis",
        status="completed", cost="0.25", context_manifest={"artifacts": []},
        messages=[{"role": "user", "parts": []}],
    )  # fmt: skip
    ToolCall.objects.create(
        agent_turn=turn, seq=1, idempotency_key=f"{turn.id}:1", tool="memory.search",
        arguments={"query": "gym"}, result={"content": "x" * 3000}, status="done",
    )  # fmt: skip
    team = client.get(f"/api/v1/projects/{project.id}/agents").json()["results"]
    analyst = next(a for a in team if a["role"] == "analyst")
    assert (analyst["turns_count"], analyst["spent"], analyst["placeholder"]) == (
        1,
        "0.250000",
        True,
    )
    detail = client.get(f"/api/v1/agents/{agent.id}").json()
    assert detail["turns"][0]["purpose"] == "analysis"
    turns = client.get(f"/api/v1/agents/{agent.id}/turns").json()["results"]
    assert turns[0]["id"] == str(turn.id)
    listed = client.get(f"/api/v1/projects/{project.id}/turns", {"status": "completed"}).json()
    assert len(listed["results"]) == 1
    full = client.get(f"/api/v1/turns/{turn.id}").json()
    assert full["context_manifest"] == {"artifacts": []}
    call = full["tool_calls"][0]
    assert (call["tool"], call["truncated"], len(call["result_excerpt"])) == (
        "memory.search", True, 2000
    )  # fmt: skip


def test_model_profiles_providers_pricing(client, monkeypatch, make_member):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-not-real")  # pragma: allowlist secret
    profiles = {p["profile"]: p for p in client.get("/api/v1/model-profiles").json()["results"]}
    assert profiles["strong"]["source"] == "default"
    assert profiles["strong"]["api_key"] == "***set***"
    assert profiles["embed"]["provider"] is None
    body = {
        "provider": "ollama",
        "model": "qwen3:14b",
        "base_url": "http://ollama:11434",
        "is_local": True,
    }
    saved = client.put("/api/v1/model-profiles/fast", body, format="json").json()
    assert (saved["configured"], saved["provider"], saved["is_local"]) == (True, "ollama", True)
    assert saved["api_key"] is None
    cli = client.put(
        "/api/v1/model-profiles/strong",
        {"provider": "anthropic-cli", "model": "opus"},
        format="json",
    )
    assert cli.status_code == 400  # opt-in required
    assert client.put("/api/v1/model-profiles/huge", body, format="json").status_code == 400
    assert (
        make_member("member").put("/api/v1/model-profiles/fast", body, format="json").status_code
        == 403
    )
    providers = {p["id"]: p for p in client.get("/api/v1/providers").json()["results"]}
    assert providers["anthropic"]["key_set"] is True
    assert "binary_found" in providers["anthropic-cli"]
    pricing = client.get("/api/v1/pricing").json()
    assert pricing["currency"] == "USD"
    assert "fake-model" in pricing["models"]["fake"]


def test_meta(client):
    body = client.get("/api/v1/meta").json()
    assert body["features"]["packages"] is False
    names = [p["name"] for p in body["processes"]]
    assert "software-house-default" in names
    phases = next(p for p in body["processes"] if p["name"] == "software-house-default")["phases"]
    assert phases[0] == {"id": "analysis", "agent": "analyst"}


def test_bootstrap_owner(monkeypatch, db):
    from io import StringIO

    from django.core.management import CommandError, call_command

    from dexterhouse.apps.accounts.models import Membership, User

    with pytest.raises(CommandError):
        call_command("bootstrap_owner", "--username", "root")
    monkeypatch.setenv("DH_OWNER_PASSWORD", "a-long-test-password")  # pragma: allowlist secret
    out = StringIO()
    call_command("bootstrap_owner", "--username", "root", stdout=out)
    assert "root owns default" in out.getvalue()
    user = User.objects.get(username="root")
    assert user.check_password("a-long-test-password")
    assert Membership.objects.get(user=user).role == "owner"
    call_command("bootstrap_owner", "--username", "root", stdout=out)  # idempotent
    assert Membership.objects.filter(user=user).count() == 1

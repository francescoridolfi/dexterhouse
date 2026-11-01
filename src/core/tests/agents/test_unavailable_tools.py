# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tools declared but not reachable, the agent's own `args_policy` and mode-gated tools."""

import json
import shutil
from pathlib import Path

import pytest
import yaml
from django.conf import settings

from dexterhouse.apps.agents.models import ToolCall
from dexterhouse.apps.agents.schemas import TurnInputs
from dexterhouse.apps.agents.services import create_agent_instance, queue_turn, run_turn
from dexterhouse.apps.agents.services.turns import turn_tools
from dexterhouse.apps.events.models import Event
from dexterhouse.apps.gateway.providers.fake import FakeResponse

from .conftest import FIXTURES, call, final

pytestmark = pytest.mark.django_db


def builtin(name: str) -> Path:
    return Path(settings.BUILTIN_DIR) / "agents" / name


def test_unreachable_tools_are_left_out_and_reported(
    organization, project, fake_profiles, tool_dirs, script
):
    broken = tool_dirs / "broken-tools"
    broken.mkdir()
    shutil.copy(tool_dirs / "echo-tools" / "README.md", broken / "README.md")
    manifest = yaml.safe_load((tool_dirs / "echo-tools" / "dexterhouse.yaml").read_text())
    manifest["name"] = "broken-tools"
    (broken / "dexterhouse.yaml").write_text(yaml.safe_dump(manifest))
    (broken / "tool.yaml").write_text(
        yaml.safe_dump(
            {
                "schema": 1,
                "name": "broken-tools",
                "transport": "stdio",
                "runs_in": "worker",
                "command": ["python", "-m", "no_such_mcp_server"],
                "permissions": [{"id": "broken.ping", "mcp_tool": "ping", "risk": "low"}],
                "network": "allowlist",
                "hosts": ["localhost"],
            }
        )
    )
    package = tool_dirs.parent / "analyst"
    shutil.copytree(FIXTURES / "agents" / "test-analyst", package)
    agent_yaml = yaml.safe_load((package / "agent.yaml").read_text())
    agent_yaml["tools"] += ["broken.ping", "git.diff"]
    (package / "agent.yaml").write_text(yaml.safe_dump(agent_yaml))
    agent = create_agent_instance(
        organization_id=organization.id, project_id=project.id, package_path=str(package)
    )
    turn = queue_turn(agent=agent, purpose="p", inputs=TurnInputs(may_ask=True), enqueue=False)
    script(FakeResponse(tool_calls=[call("broken.ping"), call("git.diff", "c2")]), final())

    run_turn(turn.id)

    turn.refresh_from_db()
    assert turn.status == "completed"
    assert turn.context_manifest["unavailable_tools"] == {
        "broken.ping": "server_unavailable",
        "git.diff": "workspace_not_ready",  # a runner tool: the project has no workspace
        "workspace.read": "workspace_not_ready",
    }
    assert "broken.ping" not in turn.context_manifest["tools"]
    results = turn.messages[3]["parts"]
    assert "tool_unavailable: broken.ping (server_unavailable)" in results[0]["content"]
    assert "tool_unavailable: git.diff (workspace_not_ready)" in results[1]["content"]
    assert not Event.objects.filter(type="security.violation").exists()


def test_tester_writes_only_test_files(organization, project, fake_profiles, tool_dirs, script):
    agent = create_agent_instance(
        organization_id=organization.id,
        project_id=project.id,
        package_path=str(builtin("tester")),
    )
    report = {
        "scope": "integration",
        "command": "uv run pytest -q",
        "exit_code": 0,
        "passed": 3,
        "failed": 0,
        "skipped": 0,
        "duration_s": 1.0,
        "verdict": "pass",
    }
    output = {
        "status": "done",
        "summary": "Suite green.",
        "artifacts": [{"kind": "test_report", "name": "test_reports/x.json", "data": report}],
        "verdict": "pass",
    }
    turn = queue_turn(
        agent=agent, purpose="p", inputs=TurnInputs(verdict_rule="test"), enqueue=False
    )
    script(
        FakeResponse(
            tool_calls=[
                call("workspace.write", "a", path="app/models.py", content="x"),
                call("workspace.write", "b", path="tests/acceptance/test_t01.py", content="x"),
                call("workspace.edit", "c", path="src/app/test_models.py", old="a", new="b"),
                call("workspace.edit", "d", path="tests/../app/models.py", old="a", new="b"),
            ]
        ),
        FakeResponse(text=json.dumps(output)),
    )

    run_turn(turn.id)

    calls = {c.call_id: c for c in ToolCall.objects.filter(agent_turn=turn)}
    assert (calls["a"].status, calls["a"].denied_reason) == ("denied", "args_policy")
    assert (calls["d"].status, calls["d"].denied_reason) == ("denied", "args_policy")
    assert calls["b"].status == calls["c"].status == "error"  # allowed, but no workspace
    assert "tool_unavailable" in calls["b"].result["content"]
    kinds = Event.objects.filter(type="security.violation").values_list("payload__kind", flat=True)
    assert list(kinds) == ["args_policy", "args_policy"]


def test_packages_install_is_offered_only_in_autonomous_mode():
    tools = ["packages.propose", "packages.install"]
    assert turn_tools(tools, "supervised") == frozenset({"packages.propose"})
    assert turn_tools(tools, "autonomous") == frozenset(tools)

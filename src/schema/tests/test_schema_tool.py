# SPDX-License-Identifier: AGPL-3.0-or-later
import pytest
from schema_helpers import DELETE, assert_invalid, load_yaml, patched

from dexterhouse_schema import Tool

TOOL = load_yaml("packages/git-tools/tool.yaml")
WORKER = patched(
    TOOL,
    {
        "name": "web-search",
        "transport": "http",
        "runs_in": "worker",
        "command": DELETE,
        "url": "https://search.example.com/mcp",
        "env": {},
        "permissions": [{"id": "web.search", "mcp_tool": "search", "risk": "high"}],
        "network": "allowlist",
        "hosts": ["search.example.com"],
    },
)


def test_doc_example_is_valid() -> None:
    tool = Tool.model_validate(TOOL)
    assert tool.permission_prefix == "git"
    assert tool.max_risk == "medium"
    assert tool.healthcheck.timeout_s == 10


def test_worker_http_tool_is_valid() -> None:
    tool = Tool.model_validate(WORKER)
    assert tool.max_risk == "high"
    assert tool.permission_prefix == "web"


@pytest.mark.parametrize(
    "command",
    [
        ["uvx", "mcp-server-git==0.6.2"],
        ["uvx", "--from", "mcp-server-git==0.6.2", "mcp-server-git"],
        ["npx", "-y", "@modelcontextprotocol/server-filesystem@2025.1.14"],
        ["npx", "@scope/server@1.2.3-beta.1", "--flag"],
        ["python", "-m", "server"],
        ["node", "server.js"],
        ["./bin/server", "--stdio"],
        ["bin/server"],
    ],
)
def test_accepted_commands(command: list[str]) -> None:
    Tool.model_validate(patched(TOOL, {"command": command}))


@pytest.mark.parametrize(
    ("command", "match"),
    [
        (["bash", "-c", "server"], "command\\[0\\]"),
        (["/usr/bin/server"], "relative"),
        (["../bin/server"], "'..'"),
        (["uvx", "mcp-server-git"], "pinned"),
        (["uvx", "mcp-server-git@latest"], "pinned"),
        (["uvx", "--from", "mcp-server-git", "mcp-server-git"], "pinned"),
        (["uvx"], "pinned"),
        (["npx", "-y", "server"], "pinned"),
        (["npx", "server@^1.2.0"], "pinned"),
        (["npx", "@scope/server"], "pinned"),
        ([], "at least 1"),
    ],
)
def test_rejected_commands(command: list[str], match: str) -> None:
    assert_invalid(Tool, patched(TOOL, {"command": command}), match)


@pytest.mark.parametrize(
    ("base", "changes", "match"),
    [
        (TOOL, {"transport": "http", "url": "https://x.example.com"}, "runs_in runner requires"),
        (TOOL, {"network": "allowlist", "hosts": ["x.example.com"]}, "runs_in runner requires"),
        (TOOL, {"command": DELETE}, "transport stdio requires"),
        (TOOL, {"url": "https://x.example.com"}, "transport stdio requires"),
        (WORKER, {"network": "none", "hosts": []}, "allowlist with explicit hosts"),
        (WORKER, {"hosts": []}, "allowlist with explicit hosts"),
        (WORKER, {"url": DELETE}, "transport http requires"),
        (WORKER, {"command": ["uvx", "a@1.0"]}, "transport http requires"),
        (WORKER, {"hosts": ["https://search.example.com"]}, "pattern"),
        (WORKER, {"url": "search.example.com"}, "http"),
        (TOOL, {"hosts": ["x.example.com"]}, "hosts must be empty"),
        (TOOL, {"permissions": []}, "at least 1"),
        (TOOL, {"permissions.1.id": "git.diff"}, "duplicate permission"),
        (TOOL, {"permissions.1.id": "github.commit"}, "must start with 'git.'"),
        (TOOL, {"permissions.1.id": "gitcommit"}, "pattern"),
        (TOOL, {"permissions.0.risk": "critical"}, "risk"),
        (TOOL, {"permissions.0.mcp_tool": ""}, "at least 1"),
        (TOOL, {"permissions.0.args_policy.repo_path.const": "${env.HOME}"}, "not allowed"),
        (TOOL, {"permissions.0.args_policy": {"ref": {"enum": ["${secrets.x}"]}}}, "not allowed"),
        (TOOL, {"env.GIT_AUTHOR_NAME": "${host.user}"}, "interpolation"),
        (TOOL, {"env": {"git_author": "x"}}, "pattern"),
        (TOOL, {"healthcheck.timeout_s": 0}, "greater than 0"),
        (TOOL, {"transport": "grpc"}, "transport"),
    ],
)
def test_invalid(base: dict[str, object], changes: dict[str, object], match: str) -> None:
    assert_invalid(Tool, patched(base, changes), match)


def test_project_interpolations_are_allowed() -> None:
    data = patched(TOOL, {"permissions.0.args_policy.repo_path": {"enum": ["${project.slug}"]}})
    Tool.model_validate(data)

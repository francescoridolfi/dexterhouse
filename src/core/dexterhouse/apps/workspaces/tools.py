# SPDX-License-Identifier: AGPL-3.0-or-later
"""`runs_in: runner` tools for the tool gateway (contracts/tools/workspace.md, git.md).

The worker never reaches a workspace itself: it sends `runner.tool.list` / `runner.tool.invoke`
to the runner, which talks MCP with the server inside the workspace (infra/runner_protocol.md).
Without a live workspace the tools are unavailable for the turn (`workspace_not_ready`).
Results are JSON for the agent; an output past 64 KB is saved as an artifact and the result
carries its id; `git.commit` and `workspace.run_tests` also emit their catalogue events, and a
commit queues a new version of the `code_graph` artifact.
"""

import json
from typing import Any

import structlog

from dexterhouse.apps.agents.models import AgentTurn
from dexterhouse.apps.agents.services.mcp_client import (
    McpError,
    RemoteTool,
    ToolOutcome,
    interpolate,
)
from dexterhouse.apps.agents.services.packages import ToolBinding
from dexterhouse.apps.workspaces import code_graph, events, services
from dexterhouse.apps.workspaces.client import get_client
from dexterhouse_schema.runner import ServerSpec, ToolInvoke, ToolList, ToolResult

logger = structlog.get_logger(__name__)

DEFAULT_TIMEOUT_S = 120
TEST_TIMEOUT_S = 900


class RunnerTools:
    """The runner side of one turn's tools (one listing per server per turn)."""

    def __init__(self, turn: AgentTurn, variables: dict[str, str] | None = None) -> None:
        self.turn = turn
        self.variables = variables or {}
        self.client = get_client()
        self._listed: dict[str, dict[str, RemoteTool] | None] = {}

    def _server(self, binding: ToolBinding) -> ServerSpec | None:
        if binding.builtin:
            return None  # the workspace's own `dexterhouse-workspace-mcp`
        tool = binding.tool
        return ServerSpec(
            name=tool.name,
            command=[interpolate(c, self.variables) for c in tool.command or []],
            env={k: interpolate(v, self.variables) for k, v in tool.env.items()},
        )

    def list_tools(self, binding: ToolBinding) -> dict[str, RemoteTool] | None:
        """The server's tools, or None when the workspace or the runner is not there."""
        key = "builtin" if binding.builtin else binding.tool.name
        if key in self._listed:
            return self._listed[key]
        workspace = services.live(self.turn.project_id)
        listed: dict[str, RemoteTool] | None = None
        if workspace is not None:
            result = self.client.call(
                "runner.tool.list",
                ToolList(workspace_id=workspace.id, server=self._server(binding)),
            )
            if result.ok:
                listed = {
                    t["name"]: RemoteTool(t["name"], t.get("description", ""), t["input_schema"])
                    for t in (result.data or {}).get("tools", [])
                }
            else:
                logger.warning(
                    "workspaces.tools_unavailable",
                    project_id=str(self.turn.project_id),
                    error=result.error.model_dump() if result.error else None,
                )
        self._listed[key] = listed
        return listed

    def call(self, binding: ToolBinding, args: dict[str, Any], seq: int) -> ToolOutcome:
        workspace = services.live(self.turn.project_id)
        if workspace is None:
            raise McpError("workspace_not_ready: the project has no live workspace")
        tool = binding.permission.mcp_tool
        timeout = DEFAULT_TIMEOUT_S
        if tool == "workspace_run_tests":
            timeout = TEST_TIMEOUT_S
        timeout = min(int(args.get("timeout_s") or timeout), TEST_TIMEOUT_S)
        if tool == "workspace_run_tests":
            events.run_started(
                self.turn, f"run_tests {args.get('scope', 'all')} {args.get('path') or ''}".strip()
            )
        services.touch(workspace)
        result = self.client.call(
            "runner.tool.invoke",
            ToolInvoke(
                workspace_id=workspace.id,
                turn_id=self.turn.id,
                seq=seq,
                tool=tool,
                args=args,
                timeout_s=timeout,
                agent_display_name=self.turn.agent_instance.display_name,
                server=self._server(binding),
            ),
            timeout_s=timeout,
        )
        error = result.error
        if (
            error is not None
            and error.code == "workspace_not_ready"
            and "runner is down" in error.detail
        ):
            raise McpError(error.detail)  # transient: the turn waits for the runner
        return self._outcome(tool, seq, result)

    def _outcome(self, tool: str, seq: int, result: ToolResult) -> ToolOutcome:
        body: dict[str, Any] = (
            dict(result.data or {}) if isinstance(result.data, dict) else {"result": result.data}
        )
        project = self.turn.project
        if result.artifact_payload:
            name = (
                f"test_runs/{self.turn.id}-{seq}.log"
                if tool == "workspace_run_tests"
                else f"tool_outputs/{self.turn.id}-{seq}.log"
            )
            artifact = events.output_artifact(
                project, name, result.artifact_payload, turn=self.turn
            )
            body["artifact_id"] = str(artifact.id)
            if tool == "workspace_run_tests":
                body["report_artifact_id"] = str(artifact.id)
                events.run_completed(project, result, artifact, turn=self.turn)
        if result.error is not None:
            body["error"] = result.error.model_dump()
        elif tool == "git_commit":
            events.commit_created(self.turn, result)
            code_graph.schedule_refresh(
                self.turn.project_id, self.turn.id, self.turn.agent_instance.role
            )
        return ToolOutcome(
            content=json.dumps(body, ensure_ascii=False, default=str),
            is_error=not result.ok,
            structured=body,
        )

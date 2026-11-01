# SPDX-License-Identifier: AGPL-3.0-or-later
"""The tool gateway: permissions, `args_policy`, idempotent `ToolCall` log, events.

An agent invokes only `AgentInstance.allowed_tools`; a call outside the list never reaches
the server: it is refused with a message to the agent and `security.violation`, and the
third refusal fails the turn (`permission`). Every call is logged under `<turn>:<seq>`, so a
resumed turn gets the recorded outcome instead of running the tool twice (ADR-0013).

A tool the agent may use but the core cannot reach (no tool package installed, a runner
tool before E-05, a server that does not start) is left out of the turn's tool list with a
warning and recorded in `unavailable`; a call to it gets `tool_unavailable`, not a refusal.
Arguments are checked against the tool package's `args_policy` and the agent's own (CD-032).
"""

import json
import re
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import structlog
from django.db import transaction

from dexterhouse.apps.agents.models import AgentTurn, ToolCall, ToolCallStatus, TurnStatus
from dexterhouse.apps.agents.services.events import emit_turn
from dexterhouse.apps.agents.services.mcp_client import McpError, McpPool, RemoteTool
from dexterhouse.apps.agents.services.packages import ToolCatalog
from dexterhouse.apps.gateway.messages import ToolCallPart, ToolResultPart, ToolSpec

logger = structlog.get_logger(__name__)

MAX_DENIALS = 3
RESULT_LIMIT = 64 * 1024
EXCERPT_CHARS = 500
_SECRET_KEY = re.compile(r"pass(word)?|secret|token|api[_-]?key|credential", re.IGNORECASE)
INTERRUPTED = "the previous attempt of this call was interrupted; its outcome is unknown"


class PermissionLimitError(RuntimeError):
    """Third refused call in the turn: the turn fails with `permission`."""


@dataclass(frozen=True)
class Denial:
    kind: str  # security.violation kind
    reason: str


class ToolGateway:
    def __init__(
        self,
        turn: AgentTurn,
        pool: McpPool,
        catalog: ToolCatalog,
        allowed: frozenset[str],
        policies: Mapping[str, dict[str, dict[str, Any]]] | None = None,
    ) -> None:
        self.turn = turn
        self.pool = pool
        self.catalog = catalog
        self.allowed = allowed
        self.policies = dict(policies or {})
        self.unavailable: dict[str, str] = {}

    # Tool specs ---------------------------------------------------------------------------

    def specs(self) -> list[ToolSpec]:
        """Schemas of the allowed tools the core can reach (worker MCP servers).

        The others are recorded in :attr:`unavailable` (`not_installed`, `runs_in_runner`,
        `server_unavailable`, `missing_on_server`) and logged once: the turn goes on without.
        """
        specs: list[ToolSpec] = []
        remote: dict[str, dict[str, RemoteTool] | None] = {}
        for permission_id in sorted(self.allowed):
            binding = self.catalog.get(permission_id)
            if binding is None:
                self.unavailable[permission_id] = "not_installed"
                continue
            if binding.tool.runs_in != "worker":
                self.unavailable[permission_id] = "runs_in_runner"  # the runner is E-05
                continue
            key = str(binding.root)
            if key not in remote:
                remote[key] = self._list_tools(binding)
            listed = remote[key]
            tool = listed.get(binding.permission.mcp_tool) if listed is not None else None
            if tool is None:
                self.unavailable[permission_id] = (
                    "server_unavailable" if listed is None else "missing_on_server"
                )
                continue
            specs.append(
                ToolSpec(
                    name=permission_id,
                    description=binding.permission.description or tool.description,
                    input_schema=tool.input_schema,
                )
            )
        if self.unavailable:
            logger.warning(
                "agents.tools_unavailable",
                turn_id=str(self.turn.id),
                agent_id=str(self.turn.agent_instance_id),
                tools=self.unavailable,
            )
        return specs

    def _list_tools(self, binding: Any) -> dict[str, RemoteTool] | None:
        """The server's tools, or None when it cannot be started or listed."""
        try:
            return {t.name: t for t in self.pool.list_tools(binding)}
        except Exception as exc:  # a missing or broken server: the turn runs without it
            logger.warning(
                "agents.tool_server_unavailable", package=binding.tool.name, error=str(exc)
            )
            return None

    # Invocation ---------------------------------------------------------------------------

    def invoke(self, seq: int, call: ToolCallPart) -> ToolResultPart:
        key = f"{self.turn.id}:{seq}"
        record = ToolCall.objects.filter(idempotency_key=key).first()
        if record is not None and record.status != ToolCallStatus.PENDING:
            return _result_part(call.id, record)
        if call.name not in self.allowed:
            denial = Denial("tool_not_allowed", f"{call.name} is not in this agent's allowed tools")
            return self._deny(seq, key, call, denial)
        violation = check_args_policy(self.policies.get(call.name, {}), call.args)
        if violation:
            return self._deny(seq, key, call, Denial("args_policy", violation))
        binding = self.catalog.get(call.name)
        if binding is None or binding.tool.runs_in != "worker" or call.name in self.unavailable:
            reason = self.unavailable.get(call.name) or (
                "not_installed" if binding is None else "runs_in_runner"
            )
            return self._unavailable(seq, key, call, f"tool_unavailable: {call.name} ({reason})")
        violation = check_args_policy(binding.permission.args_policy or {}, call.args)
        if violation:
            return self._deny(seq, key, call, Denial("args_policy", violation))
        if record is not None and binding.permission.risk != "low":
            # Interrupted mid-call and possibly not idempotent: never run it twice.
            record.status = ToolCallStatus.ERROR
            record.result = {"content": INTERRUPTED, "is_error": True}
            record.save(update_fields=["status", "result", "updated_at"])
            return _result_part(call.id, record)
        if record is None:
            record = ToolCall.objects.create(
                agent_turn=self.turn,
                seq=seq,
                idempotency_key=key,
                call_id=call.id,
                tool=call.name,
                arguments=redact(call.args),
            )
        self._set_status(TurnStatus.WAITING_TOOL)
        emit_turn(
            self.turn,
            "agent.tool.requested",
            {"turn_id": str(self.turn.id), "tool": call.name, "call_seq": seq},
        )
        started = time.monotonic()
        try:
            outcome = self.pool.call(binding, call.args)
            content, is_error = outcome.content, outcome.is_error
        except (McpError, TimeoutError) as exc:
            content, is_error = f"tool_unavailable: {exc}", True
        except Exception as exc:  # an MCP protocol error is the tool's failure, told to the agent
            logger.warning("agents.tool_error", tool=call.name, error=str(exc))
            content, is_error = f"tool error: {exc}", True
        record.duration_ms = int((time.monotonic() - started) * 1000)
        record.status = ToolCallStatus.ERROR if is_error else ToolCallStatus.DONE
        record.result = {"content": _truncate(content), "is_error": is_error}
        with transaction.atomic():
            record.save(update_fields=["duration_ms", "status", "result", "updated_at"])
            self._set_status(TurnStatus.RUNNING)
            emit_turn(
                self.turn,
                "agent.tool.used",
                {
                    "turn_id": str(self.turn.id),
                    "tool": call.name,
                    "call_seq": seq,
                    "allowed": True,
                    "duration_ms": float(record.duration_ms),
                    "result_excerpt": _excerpt(content),
                },
            )
            if call.name == "skills.read" and not is_error:
                emit_turn(
                    self.turn,
                    "agent.skill.loaded",
                    {
                        "turn_id": str(self.turn.id),
                        "agent_id": str(self.turn.agent_instance_id),
                        "skill": str(call.args.get("name", "")),
                    },
                )
        return _result_part(call.id, record)

    def _unavailable(self, seq: int, key: str, call: ToolCallPart, message: str) -> ToolResultPart:
        record = ToolCall.objects.create(
            agent_turn=self.turn,
            seq=seq,
            idempotency_key=key,
            call_id=call.id,
            tool=call.name,
            arguments=redact(call.args),
            status=ToolCallStatus.ERROR,
            result={"content": message, "is_error": True},
        )
        return _result_part(call.id, record)

    def _deny(self, seq: int, key: str, call: ToolCallPart, denial: Denial) -> ToolResultPart:
        with transaction.atomic():
            record = ToolCall.objects.create(
                agent_turn=self.turn,
                seq=seq,
                idempotency_key=key,
                call_id=call.id,
                tool=call.name,
                arguments=redact(call.args),
                allowed=False,
                status=ToolCallStatus.DENIED,
                denied_reason=denial.kind,
                result={"content": f"refused: {denial.reason}", "is_error": True},
            )
            self.turn.denied_count += 1
            self.turn.save(update_fields=["denied_count", "updated_at"])
            emit_turn(
                self.turn,
                "agent.tool.requested",
                {"turn_id": str(self.turn.id), "tool": call.name, "call_seq": seq},
            )
            emit_turn(
                self.turn,
                "agent.tool.used",
                {
                    "turn_id": str(self.turn.id),
                    "tool": call.name,
                    "call_seq": seq,
                    "allowed": False,
                    "duration_ms": 0.0,
                    "result_excerpt": "",
                    "denied_reason": denial.kind,
                },
            )
            emit_turn(
                self.turn,
                "security.violation",
                {
                    "agent_id": str(self.turn.agent_instance_id),
                    "turn_id": str(self.turn.id),
                    "tool": call.name,
                    "kind": denial.kind,
                    "count_in_turn": self.turn.denied_count,
                },
                system=True,
            )
            if self.turn.denied_count >= MAX_DENIALS:
                emit_turn(
                    self.turn,
                    "security.turn_blocked",
                    {
                        "agent_id": str(self.turn.agent_instance_id),
                        "turn_id": str(self.turn.id),
                        "violations": self.turn.denied_count,
                    },
                    system=True,
                )
        if self.turn.denied_count >= MAX_DENIALS:
            raise PermissionLimitError(f"{self.turn.denied_count} refused tool calls")
        return _result_part(call.id, record)

    def _set_status(self, status: str) -> None:
        self.turn.status = status
        self.turn.save(update_fields=["status", "updated_at"])


def check_args_policy(policy: dict[str, dict[str, Any]], args: dict[str, Any]) -> str | None:
    """The JSON Schema subset of `args_policy`: const, enum, pattern, maxLength, min/max."""
    for name, rule in policy.items():
        value = args.get(name)
        if "const" in rule and value != rule["const"]:
            return f"{name} must be {rule['const']!r}"
        if "enum" in rule and value not in rule["enum"]:
            return f"{name} must be one of {rule['enum']}"
        if isinstance(value, str):
            if "pattern" in rule and not re.search(rule["pattern"], value):
                return f"{name} does not match {rule['pattern']}"
            if "maxLength" in rule and len(value) > rule["maxLength"]:
                return f"{name} is longer than {rule['maxLength']}"
        if isinstance(value, int | float):
            if "minimum" in rule and value < rule["minimum"]:
                return f"{name} is below {rule['minimum']}"
            if "maximum" in rule and value > rule["maximum"]:
                return f"{name} is above {rule['maximum']}"
    return None


def redact(args: Any) -> Any:
    if isinstance(args, dict):
        return {k: "***" if _SECRET_KEY.search(str(k)) else redact(v) for k, v in args.items()}
    if isinstance(args, list):
        return [redact(v) for v in args]
    return args


def _truncate(content: str) -> str:
    raw = content.encode()
    if len(raw) <= RESULT_LIMIT:
        return content
    return raw[:RESULT_LIMIT].decode(errors="ignore") + "\n[truncated: result over 64 KB]"


def _excerpt(content: str) -> str:
    text = (
        json.dumps(redact(_maybe_json(content)), ensure_ascii=False)
        if content.startswith("{")
        else content
    )
    return text[:EXCERPT_CHARS]


def _maybe_json(content: str) -> Any:
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return content


def _result_part(call_id: str, record: ToolCall) -> ToolResultPart:
    result = record.result or {}
    return ToolResultPart(
        call_id=call_id,
        content=str(result.get("content", "")),
        is_error=bool(result.get("is_error")),
    )

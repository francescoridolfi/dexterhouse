# SPDX-License-Identifier: AGPL-3.0-or-later
"""Messages between the core and the runner (infra/runner_protocol.md, D-15).

The runner never imports the core: both sides validate these payloads. Queues: `runner`
(core -> runner, task names in :data:`RUNNER_TASKS`) and `core-callbacks` (runner -> core,
:data:`CALLBACK_TASKS`). Every message carries `schema`; a runner refuses another version
(operations.md: the core and the runner run the same `DH_VERSION`).
"""

import uuid
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints

PROTOCOL_SCHEMA = 1
RUNNER_QUEUE = "runner"
CALLBACK_QUEUE = "core-callbacks"
#: Output kept inline in a `ToolResult`; the rest travels as `artifact_payload` (64 KB).
OUTPUT_LIMIT = 64 * 1024

ErrorCode = Literal[
    "workspace_not_ready",
    "tool_unknown",
    "args_policy",
    "workspace_escape",
    "timeout",
    "quota_exceeded",
    "secrets_blocked",
    "conflict",
    "auth",
    "protected_branch",
    "network",
    "internal",
    "not_found",
    "invalid",
]
WorkspaceStatus = Literal[
    "requested", "creating", "ready", "busy", "idle", "error", "destroying", "destroyed"
]
DeliveryMode = Literal["push_main", "pull_request"]
Branch = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,119}$")]


def _ref(value: str) -> str:
    if ".." in value:
        raise ValueError("a ref, not a range")
    return value


def _repo_path(value: str) -> str:
    parts = value.split("/")
    if value.startswith("/") or any(p in ("", ".", "..") for p in parts):
        raise ValueError("a relative path inside the repository")
    return value


#: A branch, tag, `HEAD` or commit id; never an option (`-…`) or a range (`a..b`).
Ref = Annotated[
    str,
    StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,119}$"),
    AfterValidator(_ref),
]
#: A path inside the repository: relative, no empty, `.` or `..` segment, no control chars.
RepoPath = Annotated[
    str, StringConstraints(pattern=r"^[^\x00-\x1f]{1,1024}$"), AfterValidator(_repo_path)
]
#: Largest file `runner.system.read_file` returns (the UI is a viewer, not a download).
READ_FILE_MAX = 1024 * 1024


class Message(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_version: Literal[1] = Field(default=PROTOCOL_SCHEMA, alias="schema")

    def dump(self) -> dict[str, Any]:
        """JSON-safe dict for a Celery argument."""
        return self.model_dump(mode="json", by_alias=True)


# core -> runner ---------------------------------------------------------------------------


class Limits(Message):
    cpus: float = 2.0
    memory: str = "2g"
    disk: str = "5G"
    pids: int = 256
    exec_timeout_s: int = 120
    test_timeout_s: int = 900


class WorkspaceCreate(Message):
    project_id: uuid.UUID
    workspace_id: uuid.UUID
    stack: dict[str, Any] = Field(description="The `stack` artifact; the runner checks the image.")
    limits: Limits = Limits()


class WorkspaceDestroy(Message):
    workspace_id: uuid.UUID
    reason: Literal["completed", "archived", "inactive", "orphan"] = "completed"


class WorkspaceStatusQuery(Message):
    workspace_id: uuid.UUID


class ServerSpec(Message):
    """A third-party `runs_in: runner` tool server, started inside the workspace."""

    name: str
    command: list[str]
    env: dict[str, str] = Field(default_factory=dict)


class ToolInvoke(Message):
    workspace_id: uuid.UUID
    turn_id: uuid.UUID
    seq: int
    tool: str = Field(description="MCP tool name on the server (`workspace_exec`, `git_commit`).")
    args: dict[str, Any] = Field(default_factory=dict)
    timeout_s: int = 120
    agent_display_name: str = "Agent"
    server: ServerSpec | None = Field(default=None, description="None: the built-in server.")


class ToolList(Message):
    workspace_id: uuid.UUID
    server: ServerSpec | None = None


class BranchCreate(Message):
    workspace_id: uuid.UUID
    task_id: uuid.UUID
    branch: Branch
    from_: Branch = Field(default="main", alias="from")


class Merge(Message):
    workspace_id: uuid.UUID
    task_id: uuid.UUID
    branch: Branch
    message: str


class PullRequest(Message):
    title: str
    body: str = ""


class Deliver(Message):
    workspace_id: uuid.UUID
    mode: DeliveryMode
    remote_url: str
    token_ref: uuid.UUID | None = Field(default=None, description="SecretGrant id, never a token.")
    branch_name: Branch | None = None
    base: Branch = "main"
    pr: PullRequest | None = None


class ExitCheck(Message):
    workspace_id: uuid.UUID
    kind: Literal["tests_pass", "command_ok"]
    command: str
    timeout_s: float = 900
    probe_url: str | None = Field(
        default=None, description="A server command: start it and probe this URL inside."
    )


class CommitLog(Message):
    workspace_id: uuid.UUID
    max: int = 50
    ref: Branch = "main"


class Tree(Message):
    workspace_id: uuid.UUID
    depth: int = 3


class CodeGraph(Message):
    """The `code_graph` artifact data and/or its summary (`workspace_graph_export`)."""

    workspace_id: uuid.UUID
    include_graph: bool = True
    summary_chars: Annotated[int, Field(ge=500, le=60_000)] = 6000


class LsTree(Message):
    """Every file of the repository at `ref` (read-only: no turn, no checkout)."""

    workspace_id: uuid.UUID
    ref: Ref = "HEAD"
    max_entries: int = Field(default=20_000, ge=1, le=50_000)


class ReadFile(Message):
    """One file at `ref`; binaries and files past `max_bytes` come back without content."""

    workspace_id: uuid.UUID
    path: RepoPath
    ref: Ref = "HEAD"
    max_bytes: int = Field(default=512 * 1024, ge=1, le=READ_FILE_MAX)


# runner -> core (results and callbacks) ---------------------------------------------------


class ToolError(Message):
    code: ErrorCode
    detail: str = ""


class ToolResult(Message):
    ok: bool
    exit_code: int | None = None
    stdout: str | None = None
    stderr: str | None = None
    data: Any = None
    truncated: bool = False
    artifact_payload: str | None = Field(default=None, description="Full output past 64 KB.")
    duration_ms: int = 0
    error: ToolError | None = None

    @classmethod
    def failure(cls, code: ErrorCode, detail: str = "", **extra: Any) -> "ToolResult":
        return cls(ok=False, error=ToolError(code=code, detail=detail[:2000]), **extra)


class WorkspaceChanged(Message):
    workspace_id: uuid.UUID
    status: WorkspaceStatus
    image: str = ""
    digest: str | None = None
    container_id: str | None = None
    services: list[str] = Field(default_factory=list)
    error_detail: str | None = None


class Heartbeat(Message):
    runner_id: str
    version: str
    active_workspaces: int
    load: float = 0.0
    metrics: dict[str, float] = Field(default_factory=dict)
    workspaces: list[uuid.UUID] = Field(
        default_factory=list, description="Workspace containers this runner has (reconcile)."
    )


class SecretsBlocked(Message):
    workspace_id: uuid.UUID
    turn_id: uuid.UUID
    files: list[str]
    count: int


RUNNER_TASKS: dict[str, type[Message]] = {
    "runner.workspace.create": WorkspaceCreate,
    "runner.workspace.destroy": WorkspaceDestroy,
    "runner.workspace.status": WorkspaceStatusQuery,
    "runner.tool.invoke": ToolInvoke,
    "runner.tool.list": ToolList,
    "runner.system.branch_create": BranchCreate,
    "runner.system.merge": Merge,
    "runner.system.deliver": Deliver,
    "runner.system.exit_check": ExitCheck,
    "runner.system.commit_log": CommitLog,
    "runner.system.tree": Tree,
    "runner.system.code_graph": CodeGraph,
    "runner.system.ls_tree": LsTree,
    "runner.system.read_file": ReadFile,
}
CALLBACK_TASKS: dict[str, type[Message]] = {
    "core.runner.workspace_changed": WorkspaceChanged,
    "core.runner.heartbeat": Heartbeat,
    "core.runner.secrets_blocked": SecretsBlocked,
}

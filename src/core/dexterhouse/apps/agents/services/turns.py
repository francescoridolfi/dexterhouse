# SPDX-License-Identifier: AGPL-3.0-or-later
"""Agent turns: hire an agent, queue a turn, run it idempotently (agent_runtime.md, ADR-0013).

The public entry points are re-exported by `dexterhouse.apps.agents.services`; see
`dexterhouse/apps/agents/docs/README.md` for how the workflow engine (E-02) uses them.
"""

import uuid
from datetime import timedelta
from typing import Any, NoReturn

import structlog
from django.db import transaction
from django.db.models import Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from dexterhouse.apps.agents.models import (
    AgentInstance,
    AgentSource,
    AgentStatus,
    AgentTurn,
    ToolCall,
    ToolCallStatus,
    TurnError,
    TurnStatus,
)
from dexterhouse.apps.agents.schemas import TurnInputs
from dexterhouse.apps.agents.services.context import (
    BuiltContext,
    ContextOverflowError,
    ContextRequest,
    build_context,
    fit_history,
)
from dexterhouse.apps.agents.services.events import Speaker, emit_turn
from dexterhouse.apps.agents.services.mcp_client import McpError, McpPool
from dexterhouse.apps.agents.services.output import (
    MAX_REPROMPTS,
    OutputContractError,
    parse_output,
    reprompt_for,
    turn_context,
)
from dexterhouse.apps.agents.services.packages import (
    AgentPackage,
    PackageError,
    load_agent_package,
    load_tool_catalog,
)
from dexterhouse.apps.agents.services.tool_gateway import PermissionLimitError, ToolGateway
from dexterhouse.apps.gateway.embeddings import resolve_embedder
from dexterhouse.apps.gateway.messages import Message, TextPart, ToolCallPart, ToolSpec
from dexterhouse.apps.gateway.models import LLMCall
from dexterhouse.apps.gateway.providers import ProviderError
from dexterhouse.apps.gateway.services.gateway import CallContext, generate
from dexterhouse.apps.gateway.services.profiles import resolve_profile
from dexterhouse.apps.memory.services.search import Hit, search
from dexterhouse.apps.observability import tracing
from dexterhouse_schema.turn_output import TurnOutput

logger = structlog.get_logger(__name__)

MAX_TOOL_CALLS = 50  # hard cap per turn, whatever the package says
#: Tools offered only in autonomous mode (contracts/tools/marketplace.md).
AUTONOMOUS_ONLY_TOOLS = frozenset({"packages.install"})
IDLE_ROOM = "break_room"
CONTEXT_RETRY_FACTOR = 0.75
INITIAL_MESSAGES = 2  # system + first user message built by the context builder


class AgentTurnFailedError(RuntimeError):
    """The turn ended in `failed` (or was `cancelled`); the phase decides what to do."""

    def __init__(self, turn: AgentTurn) -> None:
        super().__init__(f"turn {turn.id} {turn.status}: {turn.error_code} {turn.error_detail}")
        self.turn_id = turn.id
        self.error_code = turn.error_code
        self.detail = turn.error_detail


class TransientTurnError(RuntimeError):
    """Provider or tool server temporarily unavailable: the turn stays resumable."""


# Hiring ---------------------------------------------------------------------------------


def create_agent_instance(
    *,
    organization_id: uuid.UUID,
    project_id: uuid.UUID,
    package_path: str,
    granted_tools: list[str] | None = None,
    display_name: str | None = None,
    source: str = AgentSource.BUILTIN,
    room: str | None = None,
    package_version_id: uuid.UUID | None = None,
    agent_id: uuid.UUID | None = None,
) -> AgentInstance:
    """Hire the agent of the package at `package_path` into a project (`agent.hired`).

    `allowed_tools` = the package's `tools` ∩ `granted_tools` (all of them when None).
    `agent_id` fixes the id (the built-in team uses one stable id per project and role).
    """
    package = load_agent_package(package_path)
    agent = package.agent
    tools = (
        sorted(set(agent.tools) & set(granted_tools))
        if granted_tools is not None
        else sorted(agent.tools)
    )
    with transaction.atomic():
        instance = AgentInstance.objects.create(
            id=agent_id or uuid.uuid4(),
            organization_id=organization_id,
            project_id=project_id,
            installed_version_id=package_version_id,
            package_name=package.name,
            package_version=package.version,
            package_path=str(package.root),
            role=agent.role,
            display_name=display_name or agent.display_name,
            model_profile=agent.model_profile,
            allowed_tools=tools,
            room=room or agent.office.room or IDLE_ROOM,
            avatar={
                "model": agent.office.avatar or "default",
                "color": agent.office.color or "#888888",
            },
            source=source,
        )
        emit_hired(instance)
    return instance


def emit_hired(instance: AgentInstance) -> None:
    _emit_system(
        instance,
        "agent.hired",
        {
            "agent_id": str(instance.id),
            "role": instance.role,
            "display_name": instance.display_name,
            "package": {"name": instance.package_name, "version": instance.package_version},
            "source": instance.source,
            "room": instance.room,
            "avatar": instance.avatar,
            "allowed_tools": instance.allowed_tools,
        },
    )


# Queueing -------------------------------------------------------------------------------


def queue_turn(
    *,
    agent: AgentInstance,
    purpose: str,
    inputs: TurnInputs | dict[str, Any],
    phase_run_id: uuid.UUID | None = None,
    task_id: uuid.UUID | None = None,
    step: str = "",
    enqueue: bool = True,
    step_run_id: uuid.UUID | None = None,
    attempt: int = 1,
) -> AgentTurn:
    """Create a `queued` turn (`agent.turn.queued`) and enqueue `run_turn` on queue `agents`.

    With `step_run_id` the call is idempotent: the same (step_run_id, attempt) returns the
    turn already created for it, whatever its status, without queueing it again.
    """
    from dexterhouse.apps.agents.tasks import run_turn_task

    if step_run_id is not None:
        existing = AgentTurn.objects.filter(step_run_id=step_run_id, step_attempt=attempt).first()
        if existing is not None:
            return existing
    data = TurnInputs.model_validate(inputs).model_dump(mode="json")
    with transaction.atomic():
        turn = AgentTurn.objects.create(
            step_run_id=step_run_id,
            step_attempt=attempt,
            organization_id=agent.organization_id,
            project_id=agent.project_id,
            agent_instance=agent,
            phase_run_id=phase_run_id,
            task_id=task_id,
            step=step,
            purpose=purpose[:120],
            inputs=data,
        )
        payload = {"turn_id": str(turn.id), "agent_id": str(agent.id), "purpose": turn.purpose}
        if task_id:
            payload["task_id"] = str(task_id)
        if step:
            payload["step"] = step
        _emit_system(agent, "agent.turn.queued", payload, correlation_id=turn.id)
        if enqueue:
            transaction.on_commit(
                lambda: run_turn_task.apply_async(args=[str(turn.id)], queue="agents")
            )
    return turn


def cancel_turn(turn_id: uuid.UUID, reason: str) -> bool:
    """Cancel a turn that has not started (project paused or archived)."""
    with transaction.atomic():
        turn = (
            AgentTurn.objects.select_for_update().select_related("agent_instance").get(id=turn_id)
        )
        if turn.status != TurnStatus.QUEUED:
            return False
        turn.status = TurnStatus.CANCELLED
        turn.finished_at = timezone.now()
        turn.save(update_fields=["status", "finished_at", "updated_at"])
        emit_turn(
            turn, "agent.turn.cancelled", {"turn_id": str(turn.id), "reason": reason}, system=True
        )
    return True


# Running --------------------------------------------------------------------------------


def run_turn(turn_id: uuid.UUID) -> TurnOutput:
    """Run (or resume) a turn to its `TurnOutput`. Idempotent: safe to call again.

    Input: the id of an `AgentTurn` created by `queue_turn`. Every step is persisted, so a
    retry after a crash resumes from the last saved message: completed LLM calls are served
    from their stored response (no new `LLMCall`), completed tool calls from their `ToolCall`
    row (never executed twice). Calling it on a `completed` turn returns the stored output.

    Output: the validated `dexterhouse_schema.TurnOutput`; the turn is then `completed`.

    Raises:
        AgentTurnFailedError: the turn is (or becomes) `failed` or `cancelled`; `error_code`
            is one of output_contract, tool_limit, timeout, provider, permission,
            context_overflow, configuration.
        TransientTurnError: provider or tool server unavailable; the turn stays `running`
            and the Celery task retries it with backoff.
    """
    turn = AgentTurn.objects.select_related("agent_instance").get(id=turn_id)
    if turn.status == TurnStatus.COMPLETED:
        return TurnOutput.model_validate(turn.output)
    if turn.status in {TurnStatus.FAILED, TurnStatus.CANCELLED}:
        raise AgentTurnFailedError(turn)
    try:
        package = load_agent_package(turn.agent_instance.package_path)
        inputs = TurnInputs.model_validate(turn.inputs)
    except (PackageError, ValueError) as exc:
        _fail(turn, TurnError.CONFIGURATION, str(exc))
    agent = turn.agent_instance
    variables = {
        "project.id": str(turn.project_id),
        "project.turn_id": str(turn.id),
        "project.organization_id": str(turn.organization_id),
        "project.data_residency": inputs.data_residency,
        "project.agent_name": agent.display_name,
    }
    with McpPool(variables, timeout_s=float(package.agent.limits.turn_timeout_s)) as pool:
        tools = ToolGateway(
            turn,
            pool,
            load_tool_catalog(organization_id=turn.organization_id),
            turn_tools(agent.allowed_tools, inputs.mode),
            policies=package.agent.args_policy,
        )
        try:
            if turn.status == TurnStatus.QUEUED:
                _start(turn, package, inputs, tools)
            else:
                turn.attempt += 1
                turn.save(update_fields=["attempt", "updated_at"])
                logger.info("agents.turn_resumed", turn_id=str(turn.id), attempt=turn.attempt)
            return _loop(turn, package, inputs, tools)
        except ContextOverflowError as exc:
            _fail(turn, TurnError.CONTEXT_OVERFLOW, str(exc))
        except PermissionLimitError as exc:
            _fail(turn, TurnError.PERMISSION, str(exc))
        except ProviderError as exc:
            if exc.retryable or exc.code == "budget":
                # Budget exhausted (F-012): the turn stays `running` and resumes once raised.
                raise TransientTurnError(str(exc)) from exc
            code = (
                TurnError.CONFIGURATION
                if exc.code in {"configuration", "authentication"}
                else TurnError.PROVIDER
            )
            _fail(turn, code, f"{exc.code}: {exc}")
        except McpError as exc:
            raise TransientTurnError(str(exc)) from exc


def turn_tools(allowed: list[str], mode: str) -> frozenset[str]:
    """The agent's allowed tools for a turn in `mode` (no `packages.install` in supervised)."""
    tools = frozenset(allowed)
    return tools if mode == "autonomous" else tools - AUTONOMOUS_ONLY_TOOLS


def fail_turn(turn_id: uuid.UUID, error_code: str, detail: str) -> None:
    """Mark a turn failed (retries exhausted) unless it already ended."""
    turn = AgentTurn.objects.select_related("agent_instance").get(id=turn_id)
    if turn.status in {TurnStatus.COMPLETED, TurnStatus.FAILED, TurnStatus.CANCELLED}:
        return
    try:
        _fail(turn, error_code, detail)
    except AgentTurnFailedError:
        pass


def notify_retry(turn_id: uuid.UUID, detail: str) -> None:
    """`agent.turn.failed(will_retry=true)`: a transient failure the task will retry."""
    turn = AgentTurn.objects.select_related("agent_instance").get(id=turn_id)
    emit_turn(
        turn,
        "agent.turn.failed",
        {
            "turn_id": str(turn.id),
            "agent_id": str(turn.agent_instance_id),
            "error_code": TurnError.PROVIDER,
            "attempt": turn.attempt,
            "will_retry": True,
        },
    )
    logger.warning("agents.turn_retry", turn_id=str(turn.id), detail=detail)


def _start(turn: AgentTurn, package: AgentPackage, inputs: TurnInputs, tools: ToolGateway) -> None:
    agent = turn.agent_instance
    specs = tools.specs()
    built = _build(turn, package, inputs, specs, factor=1.0)
    if tools.unavailable:
        built.manifest["unavailable_tools"] = dict(sorted(tools.unavailable.items()))
    room = inputs.room or agent.room or IDLE_ROOM
    with transaction.atomic():
        turn.status = TurnStatus.RUNNING
        turn.started_at = timezone.now()
        turn.attempt = 1
        turn.tool_specs = [s.model_dump() for s in built.tools]
        turn.messages = [m.model_dump(mode="json") for m in built.messages]
        turn.context_manifest = built.manifest
        turn.save()
        agent.status = AgentStatus.WORKING
        agent.save(update_fields=["status", "updated_at"])
        emit_turn(
            turn,
            "agent.moved",
            {"agent_id": str(agent.id), "from_room": IDLE_ROOM, "to_room": room, "reason": "turn"},
            system=True,
        )
        emit_turn(
            turn, "agent.status", {"agent_id": str(agent.id), "status": "working"}, system=True
        )
        emit_turn(
            turn,
            "agent.turn.started",
            {
                "turn_id": str(turn.id),
                "agent_id": str(agent.id),
                "room": room,
                "purpose": turn.purpose,
                "context": {
                    "artifacts": len(built.manifest["sections"]["artifacts"]),
                    "memory_chunks": len(built.manifest["sections"]["memory"]),
                    "notes": len(built.manifest["sections"]["notes"]),
                    "skills": built.skills,
                    "input_tokens_est": built.input_tokens_est,
                },
            },
        )


def _build(
    turn: AgentTurn, package: AgentPackage, inputs: TurnInputs, specs: list[ToolSpec], factor: float
) -> BuiltContext:
    return build_context(
        ContextRequest(
            package=package,
            inputs=inputs,
            profile=turn.agent_instance.model_profile,
            tools=specs,
            allowed_tools=frozenset(s.name for s in specs),
            memory=_memory_search(turn, inputs),
            cap_factor=factor,
        )
    )


def _memory_search(turn: AgentTurn, inputs: TurnInputs) -> Any:
    def run(query: str, k: int, exclude: Any) -> list[Hit]:
        try:
            embedder = resolve_embedder(
                turn.organization_id, turn.project_id, data_residency=inputs.data_residency
            )
            return search(
                project_id=turn.project_id,
                query=query,
                embedder=embedder,
                k=k,
                exclude_artifacts=exclude,
            ).hits
        except ProviderError as exc:  # no embedder: the turn runs without memory
            logger.warning("agents.memory_unavailable", turn_id=str(turn.id), error=str(exc))
            return []

    return run


def _loop(
    turn: AgentTurn, package: AgentPackage, inputs: TurnInputs, tools: ToolGateway
) -> TurnOutput:
    limits = package.agent.limits
    max_calls = min(limits.max_tool_calls, MAX_TOOL_CALLS)
    deadline = (turn.started_at or timezone.now()) + timedelta(seconds=limits.turn_timeout_s)
    specs = [ToolSpec.model_validate(s) for s in turn.tool_specs]
    speaker = Speaker(turn)
    while True:
        if timezone.now() > deadline:
            _fail(turn, TurnError.TIMEOUT, f"turn exceeded {limits.turn_timeout_s}s")
        messages = [Message.model_validate(m) for m in turn.messages]
        last = messages[-1]
        if last.role == "assistant":
            calls = [p for p in last.parts if isinstance(p, ToolCallPart)]
            if calls:
                _run_tools(turn, tools, messages, calls, max_calls)
                continue
            problem = reprompt_for(turn.context_manifest.get("last_stop", "end"))
            try:
                if problem:
                    raise OutputContractError(problem)
                output = parse_output(
                    last.text(), turn_context(package, inputs, asked=_asked(turn))
                )
            except OutputContractError as exc:
                if turn.reprompts >= MAX_REPROMPTS:
                    _fail(turn, TurnError.OUTPUT_CONTRACT, str(exc))
                turn.reprompts += 1
                _append(turn, Message(role="user", parts=[TextPart(text=str(exc))]), "reprompts")
                continue
            return _complete(turn, output)
        _call_llm(turn, package, inputs, tools, messages, specs, speaker)


def _call_llm(
    turn: AgentTurn,
    package: AgentPackage,
    inputs: TurnInputs,
    tools: ToolGateway,
    messages: list[Message],
    specs: list[ToolSpec],
    speaker: Speaker,
) -> None:
    agent = turn.agent_instance
    step = sum(1 for m in messages if m.role == "assistant") + 1
    allow_downgrade = bool(
        resolve_profile(turn.organization_id, turn.project_id, agent.model_profile).options.get(
            "allow_downgrade"
        )
    )
    names = {p.id: p.name for m in messages for p in m.parts if isinstance(p, ToolCallPart)}
    history = fit_history(
        messages, INITIAL_MESSAGES, turn.context_manifest["reserved_for_history"], names
    )
    try:
        out = generate(
            messages=history,
            tools=specs,
            profile=agent.model_profile,
            max_tokens=package.agent.limits.max_output_tokens,
            ctx=CallContext(
                organization_id=turn.organization_id,
                project_id=turn.project_id,
                agent_turn_id=turn.id,
                trace_id=tracing.current_trace_id(str(turn.id)),
                data_residency=inputs.data_residency,
                allow_downgrade=allow_downgrade,
            ),
            idempotency_key=f"{turn.id}:llm:{step}",
            on_event=speaker,
        )
    except ProviderError as exc:
        if exc.code != "context_length" or turn.context_manifest.get("rebuilt"):
            raise
        _rebuild(turn, package, inputs, specs, messages)
        return
    speaker.flush()
    manifest = dict(turn.context_manifest)
    manifest["last_stop"] = out.result.stop_reason
    if step > 1 and out.result.usage.cached_read:
        manifest["cache_hit"] = True
    elif manifest.get("cache_hit") is None and step > 1:
        manifest["cache_hit"] = False
    turn.context_manifest = manifest
    turn.profile_used = out.profile.profile
    _append(turn, out.result.message, "context_manifest", "profile_used", *_usage_fields(turn))


def _rebuild(
    turn: AgentTurn,
    package: AgentPackage,
    inputs: TurnInputs,
    specs: list[ToolSpec],
    messages: list[Message],
) -> None:
    """`context_length_exceeded`: recompose with the budget -25 % once (llm_gateway_detail.md)."""
    built = _build(turn, package, inputs, specs, factor=CONTEXT_RETRY_FACTOR)
    history = messages[INITIAL_MESSAGES:]
    turn.messages = [m.model_dump(mode="json") for m in [*built.messages, *history]]
    turn.context_manifest = {**built.manifest, "rebuilt": True}
    turn.save(update_fields=["messages", "context_manifest", "updated_at"])


def _run_tools(
    turn: AgentTurn,
    tools: ToolGateway,
    messages: list[Message],
    calls: list[ToolCallPart],
    max_calls: int,
) -> None:
    done_before = sum(
        1
        for m in messages[:-1]
        if m.role == "assistant"
        for p in m.parts
        if isinstance(p, ToolCallPart)
    )
    results = []
    for index, call in enumerate(calls):
        seq = done_before + index + 1
        if seq > max_calls:
            _fail(turn, TurnError.TOOL_LIMIT, f"more than {max_calls} tool calls")
        results.append(tools.invoke(seq, call))
    turn.tool_calls_count = done_before + len(calls)
    _append(turn, Message(role="tool", parts=results), "tool_calls_count")


def _append(turn: AgentTurn, message: Message, *fields: str) -> None:
    turn.messages = [*turn.messages, message.model_dump(mode="json")]
    turn.status = TurnStatus.RUNNING
    turn.save(update_fields=["messages", "status", "updated_at", *fields])


def _usage_fields(turn: AgentTurn) -> tuple[str, ...]:
    totals = LLMCall.objects.filter(agent_turn_id=turn.id, status="ok").aggregate(
        input_tokens=Coalesce(Sum("input_tokens"), 0),
        output_tokens=Coalesce(Sum("output_tokens"), 0),
        cached_tokens=Coalesce(Sum("cached_tokens"), 0),
        cost=Sum("cost"),
    )
    turn.input_tokens = totals["input_tokens"]
    turn.output_tokens = totals["output_tokens"]
    turn.cached_tokens = totals["cached_tokens"]
    turn.cost = totals["cost"] or 0
    return ("input_tokens", "output_tokens", "cached_tokens", "cost")


def _asked(turn: AgentTurn) -> bool:
    return ToolCall.objects.filter(
        agent_turn=turn, tool="project.ask", status=ToolCallStatus.DONE
    ).exists()


def _complete(turn: AgentTurn, output: TurnOutput) -> TurnOutput:
    """Persist the output and its artifacts once, even if two attempts finish together."""
    agent = turn.agent_instance
    room = TurnInputs.model_validate(turn.inputs).room or agent.room or IDLE_ROOM
    with transaction.atomic():
        current = AgentTurn.objects.select_for_update().get(pk=turn.pk)
        if current.status == TurnStatus.COMPLETED:
            return TurnOutput.model_validate(current.output)
        fields = _usage_fields(turn)
        saved = _store_artifacts(turn, output)
        turn.output = output.model_dump(mode="json")
        turn.status = TurnStatus.COMPLETED
        turn.finished_at = timezone.now()
        turn.save(update_fields=["output", "status", "finished_at", "updated_at", *fields])
        agent.status = AgentStatus.IDLE
        agent.save(update_fields=["status", "updated_at"])
        started = turn.started_at or turn.finished_at
        emit_turn(
            turn,
            "agent.turn.completed",
            {
                "turn_id": str(turn.id),
                "agent_id": str(agent.id),
                "duration_s": (turn.finished_at - started).total_seconds(),
                "input_tokens": turn.input_tokens,
                "output_tokens": turn.output_tokens,
                "cached_tokens": turn.cached_tokens,
                "cost": str(turn.cost),
                "tool_calls": turn.tool_calls_count,
                "artifacts": [
                    {"id": str(a.id), "kind": a.kind, "version": a.version} for a in saved
                ],
            },
        )
        _leave(turn, room, "idle")
    logger.info("agents.turn_completed", turn_id=str(turn.id), status=output.status)
    return output


def _store_artifacts(turn: AgentTurn, output: TurnOutput) -> list[Any]:
    """Each output artifact becomes the next version of its (kind, name), produced by the turn.

    The workflow engine reads them back by `produced_by_turn` instead of saving them again.
    """
    from dexterhouse.apps.projects.services.artifacts import save_artifact

    project = turn.project
    return [
        save_artifact(
            project,
            kind=artifact.kind,
            name=artifact.name,
            content=getattr(artifact, "content", ""),
            data=artifact.data.model_dump(mode="json") if hasattr(artifact, "data") else None,
            phase_run_id=turn.phase_run_id,
            turn_id=turn.id,
            role=turn.agent_instance.role,
        )
        for artifact in output.artifacts
    ]


def _fail(turn: AgentTurn, error_code: str, detail: str) -> NoReturn:
    agent = turn.agent_instance
    with transaction.atomic():
        turn.status = TurnStatus.FAILED
        turn.error_code = error_code
        turn.error_detail = detail[:2000]
        turn.finished_at = timezone.now()
        turn.save(
            update_fields=["status", "error_code", "error_detail", "finished_at", "updated_at"]
        )
        agent.status = AgentStatus.IDLE
        agent.save(update_fields=["status", "updated_at"])
        emit_turn(
            turn,
            "agent.turn.failed",
            {
                "turn_id": str(turn.id),
                "agent_id": str(agent.id),
                "error_code": error_code,
                "attempt": turn.attempt,
                "will_retry": False,
            },
        )
        if turn.started_at is not None:
            room = TurnInputs.model_validate(turn.inputs).room or agent.room or IDLE_ROOM
            _leave(turn, room, "idle")
    logger.warning(
        "agents.turn_failed", turn_id=str(turn.id), error_code=error_code, detail=detail[:300]
    )
    raise AgentTurnFailedError(turn)


def _leave(turn: AgentTurn, room: str, reason: str) -> None:
    agent_id = str(turn.agent_instance_id)
    emit_turn(
        turn,
        "agent.moved",
        {"agent_id": agent_id, "from_room": room, "to_room": IDLE_ROOM, "reason": reason},
        system=True,
    )
    emit_turn(turn, "agent.status", {"agent_id": agent_id, "status": "idle"}, system=True)


def _emit_system(
    instance: AgentInstance,
    event_type: str,
    payload: dict[str, Any],
    correlation_id: uuid.UUID | None = None,
) -> None:
    from dexterhouse.apps.events.schemas import Actor
    from dexterhouse.apps.events.services.publisher import emit

    emit(
        event_type,
        organization_id=instance.organization_id,
        project_id=instance.project_id,
        actor=Actor(type="system", name="agents"),
        payload=payload,
        correlation_id=correlation_id,
    )

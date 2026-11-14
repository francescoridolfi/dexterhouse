# SPDX-License-Identifier: AGPL-3.0-or-later
"""Context builder (agents/context_builder.md, CD-033): the prompt of a turn within budget.

Sections 1-5 (core prompt, package prompt, skill index, output contract, tool schemas) form
the stable prefix that is cached; sections 6-12 come from `TurnInputs` and the project
memory; what is left of the cap is reserved for the turn history (at least 15 %).
Tokens are estimated as `chars / 3.6`.
"""

import json
import math
import re
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dexterhouse.apps.agents.schemas import ArtifactInput, TurnInputs
from dexterhouse.apps.agents.services.focus import focus_inputs
from dexterhouse.apps.agents.services.packages import AgentPackage, SkillInfo, shared_skills
from dexterhouse.apps.gateway.messages import (
    Message,
    TextPart,
    ToolCallPart,
    ToolResultPart,
    ToolSpec,
)
from dexterhouse.apps.memory.mcp_server import wrap_untrusted
from dexterhouse.apps.memory.services.search import Hit
from dexterhouse_schema.artifacts import ARTIFACT_MODELS

CHARS_PER_TOKEN = 3.6
MIN_HISTORY_SHARE = 0.15
MAX_PREFIX_SHARE = 0.25
SKILL_DESCRIPTION_CHARS = 160
TOOL_DESCRIPTION_CHARS = 120
SUMMARY_CHARS = 300
PROMPTS = Path(__file__).resolve().parent.parent / "prompts"
_TASK_ID = re.compile(r"\b[TFR]-\d{2,3}\b")
_WORD = re.compile(r"[a-z0-9]{3,}")

MemorySearch = Callable[[str, int, Sequence[uuid.UUID]], list[Hit]]


@dataclass(frozen=True)
class Budget:
    cap: int
    core: int
    package: int
    skills: int
    contract: int
    tools: int
    task: int
    gates: int
    reviews: int
    artifacts: int
    memory: int
    memory_k: int
    notes: int
    tree: int


BUDGETS: dict[str, Budget] = {
    "strong": Budget(
        120_000, 1800, 3500, 800, 1200, 4000, 2000, 2000, 4000, 40_000, 12_000, 8, 2000, 2000
    ),
    "balanced": Budget(
        60_000, 1800, 3500, 800, 1200, 3000, 2000, 2000, 3000, 20_000, 8000, 6, 2000, 1500
    ),
    "fast": Budget(16_000, 1200, 2000, 400, 800, 1500, 1000, 1000, 1500, 6000, 3000, 3, 1000, 800),
}


class ContextOverflowError(ValueError):
    """The fixed sections do not fit the cap (`context_overflow`, escalation)."""


@dataclass
class ContextRequest:
    package: AgentPackage
    inputs: TurnInputs
    profile: str
    tools: list[ToolSpec]
    allowed_tools: frozenset[str]
    memory: MemorySearch | None = None
    cap_factor: float = 1.0


@dataclass
class BuiltContext:
    messages: list[Message]
    tools: list[ToolSpec]
    manifest: dict[str, Any]
    skills: list[str] = field(default_factory=list)

    @property
    def input_tokens_est(self) -> int:
        return self.manifest["cap"] - self.manifest["reserved_for_history"]


def tokens(text: str) -> int:
    return math.ceil(len(text) / CHARS_PER_TOKEN) if text else 0


def build_context(request: ContextRequest) -> BuiltContext:
    budget = BUDGETS[request.profile]
    cap = int(budget.cap * request.cap_factor)
    truncations: list[str] = []
    inputs = focus_inputs(request.inputs, truncations)

    # 1-5: stable prefix --------------------------------------------------------------
    core = (PROMPTS / ("core_short.md" if request.profile == "fast" else "core.md")).read_text(
        "utf-8"
    )
    package_prompt = request.package.system_prompt.strip()
    if tokens(package_prompt) > budget.package:
        raise ContextOverflowError(
            f"package system prompt is {tokens(package_prompt)} tokens, limit {budget.package}"
        )
    skills = available_skills(request.package, request.allowed_tools)
    skill_text = render_skills(skills)
    if tokens(skill_text) > budget.skills:
        skill_text = render_skills(skills, SKILL_DESCRIPTION_CHARS)
        truncations.append("skill descriptions cut to 160 chars")
    contract = render_contract(request.package, inputs)
    tools = request.tools
    if _tool_tokens(tools) > budget.tools:
        tools = shorten_tools(tools, TOOL_DESCRIPTION_CHARS)
        truncations.append("tool descriptions shortened")
    prefix = tokens(core) + tokens(package_prompt) + tokens(skill_text) + tokens(contract)
    prefix += _tool_tokens(tools)
    if prefix > MAX_PREFIX_SHARE * cap:
        tools = shorten_tools(tools, 60)
        skill_text = render_skills(skills, 80)
        truncations.append("prefix over 25% of cap: tool and skill descriptions reduced")
        prefix = tokens(core) + tokens(package_prompt) + tokens(skill_text) + tokens(contract)
        prefix += _tool_tokens(tools)

    # 6-8: small and decisive, always whole -----------------------------------------------
    task = _cap_text(render_task(inputs), budget.task, truncations, "task")
    gates = _take_lines(inputs.gate_answers, budget.gates)
    reviews = _take_lines(
        [json.dumps(i, ensure_ascii=False) for i in inputs.review_items], budget.reviews
    )
    fixed = prefix + tokens(task) + tokens("\n".join(gates)) + tokens("\n".join(reviews))
    if fixed > cap:
        raise ContextOverflowError(f"fixed sections need {fixed} tokens, cap {cap}")

    # 9-12 ---------------------------------------------------------------------------------
    artifacts = select_artifacts(inputs, budget.artifacts, truncations)
    whole = [uuid.UUID(str(a["id"])) for a in artifacts if a["sections"] == "whole"]
    memory = select_memory(request, budget, whole)
    notes = _take_lines([n.text for n in inputs.notes], budget.notes)
    note_ids = [str(n.id) for n in inputs.notes[: len(notes)]]
    tree = ""
    if inputs.workspace_tree and any(t.startswith("workspace.") for t in request.allowed_tools):
        tree = fit_tree(inputs.workspace_tree, budget.tree, truncations)

    def total() -> int:
        return (
            fixed
            + sum(a["tokens"] for a in artifacts)
            + sum(m["tokens"] for m in memory)
            + tokens("\n".join(notes))
            + tokens(tree)
        )

    # 6. keep at least 15 % of the cap for the history: drop tree, then memory, then artifacts
    while cap - total() < MIN_HISTORY_SHARE * cap and (tree or memory or artifacts):
        if tree:
            tree = ""
            truncations.append("tree dropped for history reserve")
        elif memory:
            memory.pop()
            truncations.append("memory chunk dropped for history reserve")
        else:
            artifacts.pop()
            truncations.append("artifact dropped for history reserve")

    user_text = render_user(inputs, task, gates, reviews, artifacts, memory, notes, tree)
    system = Message(
        role="system",
        parts=[TextPart(text=p) for p in (core, package_prompt, skill_text, contract) if p],
        cache_breakpoint=True,
    )
    used = total()
    manifest = {
        "profile": request.profile,
        "cap": cap,
        "prefix_tokens": prefix,
        "cache_hit": None,
        "sections": {
            "task": tokens(task),
            "gate_answers": tokens("\n".join(gates)),
            "review_or_tests": tokens("\n".join(reviews)),
            "artifacts": [{k: v for k, v in a.items() if k != "text"} for a in artifacts],
            "memory": [{k: v for k, v in m.items() if k != "text"} for m in memory],
            "notes": [
                {"note_id": nid, "tokens": tokens(text)}
                for nid, text in zip(note_ids, notes, strict=True)
            ],
            "tree": tokens(tree),
        },
        "skills": [s.name for s in skills],
        "tools": [t.name for t in tools],
        "reserved_for_history": cap - used,
        "truncations": truncations,
    }
    return BuiltContext(
        messages=[system, Message(role="user", parts=[TextPart(text=user_text)])],
        tools=tools,
        manifest=manifest,
        skills=[s.name for s in skills],
    )


# Sections -------------------------------------------------------------------------------


def available_skills(package: AgentPackage, tools: frozenset[str]) -> list[SkillInfo]:
    """The package's skills, then the shared built-in ones it does not shadow, whose
    `tools_required` the turn offers."""
    own = {s.name for s in package.skills}
    candidates = [*package.skills, *(s for s in shared_skills() if s.name not in own)]
    return [s for s in candidates if set(s.tools_required) <= tools]


def render_skills(skills: Sequence[SkillInfo], limit: int | None = None) -> str:
    if not skills:
        return ""
    lines = ["# Available skills (load with skills.read)"]
    for skill in skills:
        description = skill.description if limit is None else skill.description[:limit]
        lines.append(f"- {skill.name}: {description}")
    return "\n".join(lines)


def render_contract(package: AgentPackage, inputs: TurnInputs) -> str:
    contract = package.agent.output_contract
    lines = [
        "# Output contract",
        "End the turn with one JSON object (TurnOutput): "
        '{"status": "done" | "waiting_answers" | "blocked", "summary": "<= 400 chars", '
        '"artifacts": [{"kind", "name", "content" | "data"}], "verdict": null, '
        '"handoff": null | {"to_step", "notes"}, "blocked_reason": null, "assumptions_made": []}.',
        f"Allowed artifact kinds: {', '.join(contract.artifacts)}. Structured kinds carry `data`; "
        "the others carry Markdown `content`. At most 20 artifacts, 400 KB in total.",
        "`blocked_reason` is required iff status is blocked: missing_input, tool_unavailable, "
        "permission_denied, out_of_scope or budget.",
    ]
    if inputs.verdict_rule == "review":
        lines.append("`verdict` is required: approve or request_changes.")
    elif inputs.verdict_rule == "test":
        lines.append("`verdict` is required: pass or fail.")
    else:
        lines.append("`verdict` must be null for this step.")
    if not inputs.may_ask:
        lines.append(
            "Questions to the human are not allowed in this step: record assumptions instead."
        )
    structured = [contract.output_schema, *contract.artifacts]
    for kind in dict.fromkeys(k for k in structured if k in ARTIFACT_MODELS):
        schema = json.dumps(
            ARTIFACT_MODELS[kind].model_json_schema(), separators=(",", ":"), sort_keys=True
        )
        lines.append(f"JSON Schema of `{kind}` data: {schema}")
    return "\n".join(lines)


def render_task(inputs: TurnInputs) -> str:
    lines = []
    if inputs.step_description:
        lines.append(inputs.step_description)
    task = inputs.task
    if task is not None:
        head = f"{task.external_id}: {task.title}" if task.external_id else task.title
        lines.append(f"Task {head}")
        if task.iteration is not None:
            lines.append(f"Iteration {task.iteration}/{task.max_iterations or '?'}")
        if task.status:
            lines.append(f"Status: {task.status}")
        if task.description:
            lines.append(task.description)
        if task.acceptance:
            lines.append("Acceptance:\n" + "\n".join(f"- {a}" for a in task.acceptance))
        if task.files_hint:
            lines.append("Files: " + ", ".join(task.files_hint))
    lines.append(f"Mode: {inputs.mode}; questions allowed: {'yes' if inputs.may_ask else 'no'}")
    return "\n".join(lines)


def select_artifacts(
    inputs: TurnInputs, budget: int, truncations: list[str]
) -> list[dict[str, Any]]:
    """Whole artifacts in phase order while they fit; else their most relevant sections."""
    query = _words(render_task(inputs))
    task_ids = set(_TASK_ID.findall(render_task(inputs)))
    chosen: list[dict[str, Any]] = []
    left = budget
    for artifact in inputs.artifacts:
        text = _artifact_text(artifact)
        cost = tokens(text)
        entry = {
            "id": str(artifact.id),
            "kind": artifact.kind,
            "name": artifact.name,
            "version": artifact.version,
        }
        if cost <= left:
            chosen.append({**entry, "sections": "whole", "tokens": cost, "text": text})
            left -= cost
            continue
        sections = split_sections(artifact.content or "") if artifact.data is None else []
        ranked = sorted(
            range(len(sections)),
            key=lambda i: -_score(sections[i][1], query, task_ids),
        )
        picked: list[int] = []
        for index in ranked:
            cost = tokens(sections[index][1])
            if cost <= left:
                picked.append(index)
                left -= cost
        if picked:
            picked.sort()
            body = "\n\n".join(sections[i][1] for i in picked)
            if artifact.untrusted:
                body = wrap_untrusted(body, artifact.name)
            chosen.append(
                {
                    **entry,
                    "sections": [sections[i][0] for i in picked],
                    "tokens": tokens(body),
                    "text": body,
                }
            )
            truncations.append(f"{artifact.name}: {len(picked)}/{len(sections)} sections")
        else:
            headings = [h for h, _ in sections] or ["(structured data)"]
            index_text = (
                f"(not included: too large) Headings: {'; '.join(headings)}. "
                "Read it with project.artifact when available."
            )
            chosen.append(
                {**entry, "sections": [], "tokens": tokens(index_text), "text": index_text}
            )
            left -= tokens(index_text)
            truncations.append(f"{artifact.name}: heading index only")
    return chosen


def select_memory(
    request: ContextRequest, budget: Budget, exclude: list[uuid.UUID]
) -> list[dict[str, Any]]:
    if request.memory is None:
        return []
    inputs = request.inputs
    query = inputs.memory_query
    if not query and inputs.task is not None:
        query = " ".join([inputs.task.title, *inputs.task.acceptance])
    query = query or inputs.step_description
    if not query:
        return []
    chosen: list[dict[str, Any]] = []
    left = budget.memory
    for hit in request.memory(query, budget.memory_k, exclude):
        body = (
            f"[{hit.kind} {hit.name} v{hit.version}{' / ' + hit.heading if hit.heading else ''}]\n"
        )
        body += wrap_untrusted(hit.content, hit.name or hit.kind) if hit.untrusted else hit.content
        cost = tokens(body)
        if cost > left:
            continue
        left -= cost
        chosen.append(
            {
                "artifact_id": hit.artifact_id,
                "chunk": hit.chunk_index,
                "score": round(hit.score, 3),
                "weight": hit.weight,
                "tokens": cost,
                "text": body,
            }
        )
    return chosen


def fit_tree(tree: str, budget: int, truncations: list[str]) -> str:
    """Depth 2, then depth 1, then a hard cut (indentation of two spaces per level)."""
    for depth in (2, 1):
        lines = [line for line in tree.splitlines() if _indent(line) < depth]
        text = "\n".join(lines)
        if tokens(text) <= budget:
            if depth == 1:
                truncations.append("tree depth 2→1")
            return text
    truncations.append("tree cut")
    return text[: int(budget * CHARS_PER_TOKEN)]


def render_user(
    inputs: TurnInputs,
    task: str,
    gates: list[str],
    reviews: list[str],
    artifacts: list[dict[str, Any]],
    memory: list[dict[str, Any]],
    notes: list[str],
    tree: str,
) -> str:
    out = ["# Task", task]
    if gates:
        out += ["# Gate answers and comments", *gates]
    if reviews:
        out += ["# Open review findings or test failures", *reviews]
    if artifacts:
        out.append("# Artifacts")
        for a in artifacts:
            out += [f"## {a['kind']} `{a['name']}` v{a['version']}", a["text"]]
    if memory:
        out += ["# Project memory (most relevant chunks)", *(m["text"] for m in memory)]
    if notes:
        out += ["# User notes", *(f"- {n}" for n in notes)]
    if tree:
        out += ["# Workspace tree", tree]
    return "\n\n".join(out)


# History (section 13) -------------------------------------------------------------------


def message_tokens(message: Message) -> int:
    size = 0
    for part in message.parts:
        if isinstance(part, TextPart):
            size += len(part.text)
        elif isinstance(part, ToolCallPart):
            size += len(part.name) + len(json.dumps(part.args))
        elif isinstance(part, ToolResultPart):
            size += len(part.content)
    return math.ceil(size / CHARS_PER_TOKEN)


def fit_history(
    messages: list[Message], start: int, budget: int, tools_by_call: dict[str, str]
) -> list[Message]:
    """Summarise the oldest tool results (300 chars) until the history fits.

    Assistant messages, which carry decisions, are never shortened.
    """
    history = list(messages)
    used = sum(message_tokens(m) for m in history[start:])
    for index in range(start, len(history)):
        if used <= budget:
            break
        message = history[index]
        if message.role != "tool":
            continue
        parts = []
        for part in message.parts:
            if isinstance(part, ToolResultPart) and len(part.content) > SUMMARY_CHARS:
                tool = tools_by_call.get(part.call_id, "tool")
                head = f"[truncated: {tool}, {len(part.content)} chars] "
                part = replace_content(part, head + part.content[: SUMMARY_CHARS - len(head)])
            parts.append(part)
        shorter = Message(role="tool", parts=parts)
        used -= message_tokens(message) - message_tokens(shorter)
        history[index] = shorter
    return history


def replace_content(part: ToolResultPart, content: str) -> ToolResultPart:
    return part.model_copy(update={"content": content})


# Helpers --------------------------------------------------------------------------------


def shorten_tools(tools: list[ToolSpec], limit: int) -> list[ToolSpec]:
    return [
        t.model_copy(update={"description": _first_sentence(t.description, limit)}) for t in tools
    ]


def split_sections(text: str) -> list[tuple[str, str]]:
    """Markdown split at `##` headings; the preamble is a section titled `(intro)`."""
    sections: list[tuple[str, list[str]]] = [("(intro)", [])]
    for line in text.splitlines():
        if line.startswith("## "):
            sections.append((line[3:].strip(), [line]))
        else:
            sections[-1][1].append(line)
    return [(h, "\n".join(lines).strip()) for h, lines in sections if "\n".join(lines).strip()]


def _artifact_text(artifact: ArtifactInput) -> str:
    if artifact.data is not None:
        text = json.dumps(artifact.data, ensure_ascii=False, sort_keys=True)
    else:
        text = artifact.content or ""
    return wrap_untrusted(text, artifact.name) if artifact.untrusted else text


def _score(section: str, query: set[str], task_ids: set[str]) -> float:
    words = _words(section)
    overlap = len(words & query) / (len(query) or 1)
    bonus = 0.5 if task_ids & set(_TASK_ID.findall(section)) else 0.0
    return overlap + bonus


def _words(text: str) -> set[str]:
    return set(_WORD.findall(text.lower()))


def _tool_tokens(tools: list[ToolSpec]) -> int:
    return tokens(json.dumps([t.model_dump() for t in tools], separators=(",", ":")))


def _cap_text(text: str, budget: int, truncations: list[str], name: str) -> str:
    if tokens(text) <= budget:
        return text
    truncations.append(f"{name} cut to budget")
    return text[: int(budget * CHARS_PER_TOKEN)]


def _take_lines(items: Sequence[str], budget: int) -> list[str]:
    taken: list[str] = []
    used = 0
    for item in items:
        cost = tokens(item)
        if used + cost > budget:
            break
        taken.append(item)
        used += cost
    return taken


def _indent(line: str) -> int:
    return (len(line) - len(line.lstrip(" "))) // 2


def _first_sentence(text: str, limit: int) -> str:
    sentence = re.split(r"(?<=[.!?])\s", text, maxsplit=1)[0]
    return sentence[:limit]


__all__ = [
    "BUDGETS",
    "BuiltContext",
    "ContextOverflowError",
    "ContextRequest",
    "build_context",
    "fit_history",
]

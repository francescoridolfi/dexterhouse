# SPDX-License-Identifier: AGPL-3.0-or-later
"""Task focus for loop steps (developer, reviewer, tester): the board and the architecture
reduced to what the current task needs, before the context builder spends its budget.

- `task_board`: the current task and the tasks it depends on; the other ids stay listed.
- `architecture`: the preamble and the `FOCUS_SECTIONS` sections closest to the task (word
  overlap with title, description, acceptance and files); the other headings stay listed.

The agent can still read the whole artifact with `project.artifact`.
"""

import re
from typing import Any

from dexterhouse.apps.agents.schemas import ArtifactInput, TaskInput, TurnInputs

FOCUS_SECTIONS = 4
_WORD = re.compile(r"[a-z0-9_./-]{3,}")
_STOP = frozenset({"the", "and", "for", "with", "that", "this", "are", "from", "not", "use"})


def focus_inputs(inputs: TurnInputs, truncations: list[str]) -> TurnInputs:
    """`inputs` with the task board and architecture focused on `inputs.task` (if any)."""
    task = inputs.task
    if task is None or not task.external_id:
        return inputs
    artifacts = []
    for artifact in inputs.artifacts:
        if artifact.kind == "task_board" and isinstance(artifact.data, dict):
            artifact = _focus_board(artifact, task.external_id, truncations)
        elif artifact.kind == "architecture" and artifact.content:
            artifact = _focus_markdown(artifact, task, truncations)
        artifacts.append(artifact)
    return inputs.model_copy(update={"artifacts": artifacts})


def _focus_board(artifact: ArtifactInput, task_id: str, truncations: list[str]) -> ArtifactInput:
    tasks = [t for t in artifact.data.get("tasks") or [] if isinstance(t, dict)]
    current = next((t for t in tasks if t.get("external_id") == task_id), None)
    if current is None:
        return artifact
    wanted = {task_id, *current.get("depends_on", [])}
    kept = [t for t in tasks if t.get("external_id") in wanted]
    others = [t.get("external_id") for t in tasks if t.get("external_id") not in wanted]
    data: dict[str, Any] = {"tasks": kept}
    if others:
        data["other_tasks"] = others
        truncations.append(f"{artifact.name}: {task_id} and its dependencies only")
    return artifact.model_copy(update={"data": data})


def _focus_markdown(
    artifact: ArtifactInput, task: TaskInput, truncations: list[str]
) -> ArtifactInput:
    preamble, sections = _split(artifact.content or "")
    if len(sections) <= FOCUS_SECTIONS:
        return artifact
    query = _words(" ".join([task.title, task.description, *task.acceptance, *task.files_hint]))
    ranked = sorted(range(len(sections)), key=lambda i: -len(_words(sections[i][1]) & query))
    keep = sorted(ranked[:FOCUS_SECTIONS])
    omitted = [sections[i][0] for i in range(len(sections)) if i not in keep]
    body = [preamble, *(sections[i][1] for i in keep)]
    body.append(f"(Other sections, read with project.artifact if needed: {'; '.join(omitted)}.)")
    truncations.append(f"{artifact.name}: {len(keep)}/{len(sections)} sections for the task")
    return artifact.model_copy(update={"content": "\n\n".join(p for p in body if p)})


def _split(text: str) -> tuple[str, list[tuple[str, str]]]:
    """The text before the first `##` heading, and the `##` sections (heading, text)."""
    preamble: list[str] = []
    sections: list[tuple[str, list[str]]] = []
    for line in text.splitlines():
        if line.startswith("## "):
            sections.append((line[3:].strip(), [line]))
        elif sections:
            sections[-1][1].append(line)
        else:
            preamble.append(line)
    return "\n".join(preamble).strip(), [(h, "\n".join(b).strip()) for h, b in sections]


def _words(text: str) -> set[str]:
    return set(_WORD.findall(text.lower())) - _STOP

# SPDX-License-Identifier: AGPL-3.0-or-later
"""Loop steps see their task's slice of the task board and of architecture.md."""

import uuid

from dexterhouse.apps.agents.schemas import ArtifactInput, TaskInput, TurnInputs
from dexterhouse.apps.agents.services.focus import FOCUS_SECTIONS, focus_inputs

BOARD = {
    "tasks": [
        {"external_id": f"T-0{i}", "title": f"Task {i}", "depends_on": deps}
        for i, deps in [(1, []), (2, ["T-01"]), (3, ["T-02"]), (4, [])]
    ],
    "notes": "four tasks",
}
SECTIONS = ["Overview", "Stack", "Modules", "Data model", "Interfaces", "Layout", "Risks"]
ARCHITECTURE = "# Architecture\n\nIntro.\n\n" + "\n\n".join(
    f"## {h}\n\nGeneric text about {h.lower()}." for h in SECTIONS
)
ARCHITECTURE += "\n\nThe operations module computes results with operations.py."


def inputs(task: TaskInput | None) -> TurnInputs:
    return TurnInputs(
        step_description="Implement.",
        task=task,
        artifacts=[
            ArtifactInput(id=uuid.uuid4(), kind="task_board", name="task_board.json", data=BOARD),
            ArtifactInput(
                id=uuid.uuid4(), kind="architecture", name="architecture.md", content=ARCHITECTURE
            ),
        ],
        verdict_rule="none",
    )


TASK = TaskInput(
    external_id="T-03",
    title="Operations",
    description="Implement the operations module.",
    files_hint=["src/calc/operations.py"],
)


def test_board_keeps_the_task_and_its_dependencies():
    notes: list[str] = []
    board, _ = focus_inputs(inputs(TASK), notes).artifacts
    assert [t["external_id"] for t in board.data["tasks"]] == ["T-02", "T-03"]
    assert board.data["other_tasks"] == ["T-01", "T-04"]
    assert "task_board.json: T-03 and its dependencies only" in notes


def test_architecture_keeps_the_relevant_sections_and_lists_the_others():
    notes: list[str] = []
    _, architecture = focus_inputs(inputs(TASK), notes).artifacts
    text = architecture.content
    assert text.startswith("# Architecture\n\nIntro.")
    assert "operations.py" in text  # the section that mentions the task's file
    assert text.count("\n## ") == FOCUS_SECTIONS
    assert "read with project.artifact" in text
    assert f"architecture.md: {FOCUS_SECTIONS}/{len(SECTIONS)} sections for the task" in notes


def test_steps_without_a_task_see_everything():
    original = inputs(None)
    assert focus_inputs(original, []) is original

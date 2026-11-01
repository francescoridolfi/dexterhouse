# SPDX-License-Identifier: AGPL-3.0-or-later
"""`process.yaml`: a process as a graph of phases.

Referenced agent roles are checked by the core before a project starts (F-001), not here.
"""

from typing import Annotated, Literal

from pydantic import Field, model_validator

from dexterhouse_schema.common import (
    ARTIFACT_KINDS,
    ExtensibleModel,
    Ident,
    NonEmptyStr,
    PackageName,
    SchemaVersion,
    SemVer,
    StrictModel,
)

ExitCondition = Literal["artifacts_present", "tests_pass", "command_ok", "none"]
ApproveAction = Literal["install_proposed_packages", "hire", "merge", "deliver"]
RejectAction = Literal["reopen_implementation", "fail"]
When = Literal["hired", "always", "never"]


def _check_kinds(kinds: list[str], where: str) -> None:
    unknown = sorted(set(kinds) - ARTIFACT_KINDS)
    if unknown:
        raise ValueError(f"{where}: unknown artifact kind(s) in produces: {', '.join(unknown)}")


class Step(StrictModel):
    """One sequential step of a phase. A bare role string is shorthand for `{agent: role}`."""

    agent: Ident
    step: Ident | None = None
    produces: list[str] = Field(default_factory=list)
    exit: ExitCondition | None = None
    command: NonEmptyStr | None = None
    when: When | None = Field(default=None, description="Only inside `after_gate`.")

    @model_validator(mode="after")
    def _check(self) -> "Step":
        _check_kinds(self.produces, f"step {self.step or self.agent}")
        if self.exit == "command_ok" and self.command is None:
            raise ValueError("exit command_ok requires `command`")
        return self


class Gate(StrictModel):
    id: Ident
    default: Literal["required", "optional"] = "required"
    on_approve: list[ApproveAction] = Field(default_factory=list)
    on_reject: RejectAction | None = None


class Phase(StrictModel):
    """A phase runs one `agent` or a list of `steps` (never both)."""

    id: Ident
    agent: Ident | None = None
    steps: Annotated[list[Ident | Step], Field(min_length=1)] | None = None
    needs: list[Ident] = Field(default_factory=list)
    may_ask: bool = False
    workspace: bool = False
    produces: list[str] = Field(default_factory=list)
    exit: ExitCondition | None = None
    command: NonEmptyStr | None = None
    gate: Gate | None = None
    after_gate: list[Step] = Field(default_factory=list)
    type: Literal["loop"] | None = Field(default=None, description="Absent: sequential.")
    over: str | None = Field(default=None, description="Artifact kind iterated by a loop.")
    max_iterations: Annotated[int, Field(ge=1, le=10)] | None = None
    on_exhausted: Literal["escalate", "fail"] | None = None

    def step_list(self) -> list[Step]:
        """Steps with the string shorthand expanded (the `agent` phase as a single step)."""
        if self.steps is None:
            return [Step(agent=self.agent)] if self.agent else []
        return [Step(agent=s) if isinstance(s, str) else s for s in self.steps]

    def produced_kinds(self) -> set[str]:
        """Kinds produced by the phase, its steps and its after-gate steps."""
        kinds = set(self.produces)
        for step in [*self.step_list(), *self.after_gate]:
            kinds.update(step.produces)
        return kinds

    @model_validator(mode="after")
    def _check(self) -> "Phase":
        if (self.agent is None) == (self.steps is None):
            raise ValueError(f"phase {self.id}: exactly one of `agent` or `steps` is required")
        _check_kinds(self.produces, f"phase {self.id}")
        if self.exit == "command_ok" and self.command is None:
            raise ValueError(f"phase {self.id}: exit command_ok requires `command`")
        loop_fields = (self.over, self.max_iterations, self.on_exhausted)
        if self.type == "loop":
            if any(f is None for f in loop_fields):
                raise ValueError(
                    f"phase {self.id}: type loop requires over, max_iterations, on_exhausted"
                )
            if self.over not in ARTIFACT_KINDS:
                raise ValueError(f"phase {self.id}: over {self.over!r} is not an artifact kind")
        elif any(f is not None for f in loop_fields):
            raise ValueError(f"phase {self.id}: over/max_iterations/on_exhausted need type loop")
        if self.after_gate and self.gate is None:
            raise ValueError(f"phase {self.id}: after_gate requires a gate")
        if any(s.when is not None for s in self.step_list()):
            raise ValueError(f"phase {self.id}: `when` is only allowed in after_gate")
        return self


class Process(ExtensibleModel):
    """Process definition (`kind: process`)."""

    schema_version: SchemaVersion = Field(alias="schema")
    name: PackageName
    version: SemVer
    rooms: dict[Ident, Ident] = Field(
        default_factory=dict, description="Room override per phase id."
    )
    phases: Annotated[list[Phase], Field(min_length=1)]

    @model_validator(mode="after")
    def _check_graph(self) -> "Process":
        ids = [p.id for p in self.phases]
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        if dupes:
            raise ValueError(f"duplicate phase id(s): {', '.join(dupes)}")
        known = set(ids)
        for phase in self.phases:
            missing = sorted(set(phase.needs) - known)
            if missing:
                raise ValueError(f"phase {phase.id}: needs unknown phase(s) {', '.join(missing)}")
        for room_phase in self.rooms:
            if room_phase not in known:
                raise ValueError(f"rooms: unknown phase {room_phase!r}")
        gates = [p.gate.id for p in self.phases if p.gate]
        dupes = sorted({g for g in gates if gates.count(g) > 1})
        if dupes:
            raise ValueError(f"duplicate gate id(s): {', '.join(dupes)}")
        cycle = self._find_cycle()
        if cycle:
            raise ValueError(f"phase graph has a cycle: {' -> '.join(cycle)}")
        return self

    def _find_cycle(self) -> list[str] | None:
        needs = {p.id: p.needs for p in self.phases}
        state: dict[str, int] = {}  # 1 = visiting, 2 = done

        def visit(node: str, path: list[str]) -> list[str] | None:
            if state.get(node) == 1:
                return [*path[path.index(node) :], node]
            if state.get(node) == 2:
                return None
            state[node] = 1
            for dep in needs[node]:
                found = visit(dep, [*path, node])
                if found:
                    return found
            state[node] = 2
            return None

        for phase_id in needs:
            found = visit(phase_id, [])
            if found:
                return found
        return None

    def ancestors(self, phase_id: str) -> set[str]:
        """Phase ids reachable through `needs` (transitively) from `phase_id`."""
        needs = {p.id: p.needs for p in self.phases}
        seen: set[str] = set()
        todo = list(needs[phase_id])
        while todo:
            current = todo.pop()
            if current not in seen:
                seen.add(current)
                todo.extend(needs[current])
        return seen

    def brief_requirements(self) -> dict[str, list[str]]:
        """Inputs the project brief must provide, mapped to the phases that need them.

        A `workspace: true` phase with no upstream (via `needs`) phase producing `stack`
        makes `stack` a requirement of the process instead of an error.
        """
        by_id = {p.id: p for p in self.phases}
        missing = [
            p.id
            for p in self.phases
            if p.workspace
            and not any("stack" in by_id[a].produced_kinds() for a in self.ancestors(p.id))
        ]
        return {"stack": missing} if missing else {}

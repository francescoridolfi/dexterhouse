# ADR-0004: Processes as YAML state machines

- Status: accepted · Date: 2026-10-31

## Context
Competing projects hard-code the analysis→development→testing sequence; changing methodology requires a fork. The project owner wants the flow to be shareable like agents.

## Decision
A process is a `kind: process` package with phases, dependencies (`needs`), assigned agents, expected artifacts, verifiable exit criteria, gates and bounded loops. The core contains a generic interpreter; state lives in `ProcessRun`/`PhaseRun`.

## Alternatives considered
- BPMN engine (Camunda/Zeebe): complete but heavy, another platform to operate.
- Airflow-style DAG: no native human gates or loops with escalation.
- Agent graph in code (LangGraph): powerful, but neither declarative nor installable from a marketplace.

## Consequences
+ Scrum, Kanban, "refactoring only", "security audit only" become packages of a few lines.
+ Exit criteria verifiable by the core (green tests, artifact present) reduce hallucinated "done".
− Expressiveness limited by design: no arbitrary conditions in 1.0; a `when` with simple expressions may arrive in 1.x.

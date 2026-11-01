# SPDX-License-Identifier: AGPL-3.0-or-later
"""Parse and validate the `TurnOutput` that ends a turn (turn_output.md, CD-030)."""

from pydantic import ValidationError

from dexterhouse.apps.agents.schemas import TurnInputs
from dexterhouse.apps.agents.services.packages import AgentPackage
from dexterhouse_schema.context import TurnContext
from dexterhouse_schema.turn_output import TurnOutput, extract_turn_json, validate_turn_output

MAX_REPROMPTS = 2


class OutputContractError(ValueError):
    """The final message is not a valid TurnOutput; `str()` is the reprompt text."""


def turn_context(package: AgentPackage, inputs: TurnInputs, asked: bool) -> TurnContext:
    return TurnContext(
        allowed_kinds=frozenset(package.agent.output_contract.artifacts),
        verdict=inputs.verdict_rule,
        asked=asked,
        known_finding_ids=frozenset(inputs.known_finding_ids)
        if inputs.known_finding_ids is not None
        else None,
        installed_roles=frozenset(inputs.installed_roles)
        if inputs.installed_roles is not None
        else None,
        task_ids=frozenset(inputs.task_ids) if inputs.task_ids is not None else None,
        stack_test_command=inputs.stack_test_command,
    )


def parse_output(text: str, context: TurnContext) -> TurnOutput:
    """The TurnOutput ending `text`.

    Raises:
        OutputContractError: no JSON object at the end, or schema/rule violations.
    """
    try:
        raw = extract_turn_json(text)
    except ValueError as exc:
        raise OutputContractError(
            "Your last message did not end with a JSON object. Reply with only the TurnOutput JSON."
        ) from exc
    try:
        return validate_turn_output(raw, context)
    except ValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(str(p) for p in error['loc']) or 'output'}: {error['msg']}"
            for error in exc.errors()
        )
        raise OutputContractError(
            f"Your TurnOutput is invalid: {problems}. "
            "Fix it and reply with only the corrected JSON."
        ) from exc


def reprompt_for(stop_reason: str) -> str | None:
    """Reprompt text for a final answer that stopped abnormally."""
    if stop_reason == "max_tokens":
        return (
            "Your answer was cut at the output limit. Reply with only the TurnOutput JSON, shorter."
        )
    if stop_reason == "refusal":
        return (
            "The previous answer was declined. If you cannot do the task, return a TurnOutput with "
            "status blocked and blocked_reason out_of_scope."
        )
    return None

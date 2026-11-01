# SPDX-License-Identifier: AGPL-3.0-or-later
import pytest
from schema_helpers import DELETE, assert_invalid, load_yaml, patched

from dexterhouse_schema import Agent

AGENT = load_yaml("packages/security-reviewer/agent.yaml")


def test_doc_example_is_valid() -> None:
    agent = Agent.model_validate(AGENT)
    assert agent.role == "security_reviewer"
    assert agent.output_contract.output_schema == "review"
    assert agent.i18n.display_name == {"it": "Revisore sicurezza"}


def test_minimal_agent_uses_defaults() -> None:
    minimal = {
        "schema": 1,
        "role": "writer",
        "display_name": "Writer",
        "model_profile": "fast",
        "prompts": {"system": "prompts/system.md"},
        "output_contract": {"artifacts": ["release_notes"], "schema": "markdown"},
    }
    agent = Agent.model_validate(minimal)
    assert agent.limits.max_tool_calls == 40
    assert agent.tools == []
    assert agent.capabilities.may_ask is False


def test_assumptions_is_an_accepted_output_schema() -> None:
    data = patched(
        AGENT, {"output_contract": {"artifacts": ["assumptions"], "schema": "assumptions"}}
    )
    assert Agent.model_validate(data).output_contract.output_schema == "assumptions"


@pytest.mark.parametrize(
    ("changes", "match"),
    [
        ({"role": "Security-Reviewer"}, "pattern"),
        ({"model_profile": "huge"}, "model_profile"),
        ({"tools": ["workspace"]}, "pattern"),
        ({"tools": ["git.diff", "git.diff"]}, "duplicate tools"),
        ({"skills": ["owasp-top10", "owasp-top10"]}, "duplicate skills"),
        ({"skills": ["OWASP"]}, "pattern"),
        ({"prompts.system": DELETE}, "system"),
        ({"prompts.system": "/etc/prompt.md"}, "relative"),
        ({"prompts.examples": "../examples.md"}, "'..'"),
        ({"output_contract.artifacts": []}, "at least 1"),
        ({"output_contract.artifacts": ["review", "poem"]}, "unknown artifact kind"),
        ({"output_contract.schema": "poem"}, "schema must be one of"),
        ({"output_contract.schema": "test_report"}, "must be listed in artifacts"),
        ({"limits.max_tool_calls": 51}, "less than or equal to 50"),
        ({"limits.turn_timeout_s": 901}, "less than or equal to 900"),
        ({"limits.max_output_tokens": 0}, "greater than or equal to 1"),
        ({"office.color": "purple"}, "pattern"),
        ({"office.room": "Review Corner"}, "pattern"),
        ({"capabilities.may_ask": "yes"}, "boolean"),
        ({"capabilities.writes_host": True}, "Extra inputs"),
        ({"i18n.display_name": {"italian": "x"}}, "pattern"),
        ({"requires_tools": ["Git"]}, "pattern"),
        ({"unknown": 1}, "Extra inputs"),
    ],
)
def test_invalid(changes: dict[str, object], match: str) -> None:
    assert_invalid(Agent, patched(AGENT, changes), match)

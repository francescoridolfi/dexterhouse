# SPDX-License-Identifier: AGPL-3.0-or-later
"""Marketplace texts are data: wrapping and detection of instructions addressed to agents.

Every text that comes from a package (description, README, permission descriptions) reaches
an agent inside `<<untrusted source="marketplace">>…<</untrusted>>` (contracts/tools/
marketplace.md); markers written by the author are neutralised so a README cannot close the
block early. :func:`flags` finds the usual prompt-injection phrasings: a flagged package is
reported to the Recruiter (`flags`) and logged, the signal of `package.flagged` (1.x).
"""

import re

OPEN = '<<untrusted source="marketplace">>'
CLOSE = "<</untrusted>>"
_MARKER = re.compile(r"<<\s*/?\s*untrusted", re.IGNORECASE)
_PATTERNS: dict[str, re.Pattern[str]] = {
    "ignore_instructions": re.compile(
        r"\b(ignore|disregard|forget|override)\b[^.\n]{0,40}\b"
        r"(instructions?|prompts?|rules|guidelines|constraints)\b",
        re.IGNORECASE,
    ),
    "addresses_the_agent": re.compile(
        r"\b(dear|attention|note to|hey|to the)\s+(ai|llm|agent|assistant|recruiter|model)\b"
        r"|\b(ai|llm|language model)s?\s*(agents?|assistants?)?\s*(must|should|reading this)\b"
        r"|\byou are (now )?(an?|the) (ai|assistant|agent|recruiter|language model)\b",
        re.IGNORECASE,
    ),
    "system_prompt": re.compile(r"\b(system prompt|developer message|jailbreak)\b", re.IGNORECASE),
    "tool_directive": re.compile(
        r"\b(call|run|invoke|use)\b[^.\n]{0,20}\b(packages\.install|packages_install|"
        r"marketplace\.|workspace\.|git\.push|the tool)\b",
        re.IGNORECASE,
    ),
    "marker_spoofing": _MARKER,
}


def neutralise(text: str) -> str:
    """Break any `<<untrusted` / `<</untrusted` written by the author."""
    return _MARKER.sub(lambda m: m[0].replace("<<", "«"), text)


def wrap(text: str | None) -> str | None:
    """`text` inside the untrusted block (None and "" unchanged)."""
    if not text:
        return text
    return f"{OPEN}\n{neutralise(text)}\n{CLOSE}"


def flags(text: str | None) -> list[str]:
    """The kinds of agent-directed instructions found in `text`, sorted."""
    if not text:
        return []
    return sorted(name for name, pattern in _PATTERNS.items() if pattern.search(text))

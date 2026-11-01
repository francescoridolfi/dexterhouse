# SPDX-License-Identifier: AGPL-3.0-or-later
"""Content rules for prompt and skill text.

:data:`FORBIDDEN_PATTERNS` is the maintained list of instructions that try to switch off
the core's guarantees (permissions, gates, the core system prompt). A match preceded by
a negation (`do not ignore the gates`) is not reported. Secret scanning is done by
detect-secrets in the registry CI, not here.
"""

import re
from dataclasses import dataclass

MAX_SYSTEM_PROMPT_CHARS = 12_000

_VERBS = r"ignore|disregard|forget|override|bypass|circumvent|skip|evade|work around"
_TARGETS = (
    r"permissions?|gates?|approvals?|allowed[ _]tools|sandbox|escalations?"
    r"|(?:core |system |previous |prior |above |earlier |all )+(?:instructions|prompts?|rules)"
    r"|system prompt|core prompt"
)

#: (pattern id, compiled regex). Matching is case-insensitive and stays within a sentence.
FORBIDDEN_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "override-core-rules",
        re.compile(rf"\b(?:{_VERBS})\b[^.\n]{{0,40}}?\b(?:{_TARGETS})\b", re.IGNORECASE),
    ),
    (
        "disobey-core-rules",
        re.compile(
            r"\b(?:do not|don't|never|stop)\s+(?:follow|obey|respect|comply with)\b"
            r"[^.\n]{0,30}?\b(?:system prompt|core prompt|permissions?|gates?|instructions)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "unlisted-tools",
        re.compile(
            r"\b(?:call|use|invoke)\b[^.\n]{0,20}\btools?\b[^.\n]{0,10}\bnot (?:listed|allowed)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "untrusted-as-instructions",
        re.compile(
            r"\btreat\b[^.\n]{0,30}\buntrusted\b[^.\n]{0,30}\bas (?:instructions|commands)\b",
            re.IGNORECASE,
        ),
    ),
)
_NEGATION_RE = re.compile(r"\b(?:not|never|no|n't|without)\s*(?:\w+\s+){0,2}$", re.IGNORECASE)


@dataclass(frozen=True)
class PatternMatch:
    pattern_id: str
    line: int
    excerpt: str


def scan_text(text: str) -> list[PatternMatch]:
    """Return every forbidden pattern found in `text` (1-based line numbers)."""
    found: list[PatternMatch] = []
    for pattern_id, regex in FORBIDDEN_PATTERNS:
        for match in regex.finditer(text):
            before = text[max(0, match.start() - 30) : match.start()]
            if pattern_id == "override-core-rules" and _NEGATION_RE.search(before):
                continue
            line = text.count("\n", 0, match.start()) + 1
            found.append(PatternMatch(pattern_id, line, match.group(0)[:80]))
    return found

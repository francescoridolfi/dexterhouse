# SPDX-License-Identifier: AGPL-3.0-or-later
"""Facts of JS/TS, Go and Java files from line regexes (fallback: no tree-sitter in the images).

What is found: import specifiers and the names they bind, top-level declarations (classes,
functions, arrow constants, interfaces, types, enums; Go methods by receiver) and `extends`.
Calls are only the uses of imported or top-level names (`name(`, `new Name`, `<Name`),
attributed to the file (caller ""): regexes cannot see function scopes.
"""

import re
from typing import Any

_ID = r"[A-Za-z_$][\w$]*"
_JS_FROM = re.compile(
    r"^\s*(?:import|export)\s+(?:type\s+)?([\w$*{}\s,]+?)\s+from\s+['\"]([^'\"]+)['\"]",
    re.MULTILINE,
)
_JS_BARE = re.compile(
    r"^\s*import\s+['\"]([^'\"]+)['\"]|\b(?:require|import)\(\s*['\"]([^'\"]+)['\"]\s*\)",
    re.MULTILINE,
)
_JS_DECLS = [
    (
        re.compile(
            rf"^(?:export\s+)?(?:default\s+)?(?:abstract\s+)?class\s+({_ID})"
            rf"(?:<[^>{{]*>)?(?:\s+extends\s+({_ID}(?:\.{_ID})*))?"
        ),
        "class",
    ),
    (
        re.compile(rf"^(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s*\*?\s*({_ID})"),
        "function",
    ),
    (
        re.compile(
            rf"^(?:export\s+)?(?:const|let|var)\s+({_ID})\s*(?::[^=]+)?=\s*(?:async\s+)?"
            rf"(?:function\b|\([^)]*\)\s*(?::[^=]+)?=>|{_ID}\s*=>)"
        ),
        "function",
    ),
    (re.compile(rf"^(?:export\s+)?(?:declare\s+)?interface\s+({_ID})"), "interface"),
    (re.compile(rf"^(?:export\s+)?(?:declare\s+)?type\s+({_ID})\s*(?:<[^=]*>)?\s*="), "type"),
    (re.compile(rf"^(?:export\s+)?(?:declare\s+)?(?:const\s+)?enum\s+({_ID})"), "enum"),
]
_GO_IMPORT = re.compile(r"^\s*(?:import\s+)?(?:([\w.]+)\s+)?\"([^\"]+)\"\s*$", re.MULTILINE)
_GO_DECLS = [
    (re.compile(r"^func\s+\(\s*\w*\s*\*?\s*(\w+)(?:\[[^\]]*\])?\s*\)\s*(\w+)"), "method"),
    (re.compile(r"^func\s+(\w+)"), "function"),
    (re.compile(r"^type\s+(\w+)(?:\[[^\]]*\])?\s+struct\b"), "struct"),
    (re.compile(r"^type\s+(\w+)(?:\[[^\]]*\])?\s+interface\b"), "interface"),
    (re.compile(r"^type\s+(\w+)\b"), "type"),
]
_JAVA_IMPORT = re.compile(r"^\s*import\s+(?:static\s+)?([\w.]+?)(\.\*)?\s*;", re.MULTILINE)
_JAVA_DECL = re.compile(
    r"^\s*(?:(?:public|protected|private|abstract|final|static|sealed|non-sealed)\s+)*"
    r"(class|interface|enum|record)\s+(\w+)(?:<[^>{]*>)?(?:\([^)]*\))?(?:\s+extends\s+([\w.]+))?"
)


def _js_binds(clause: str) -> dict[str, str]:
    binds: dict[str, str] = {}
    clause = clause.strip()
    if clause.startswith("*"):
        if alias := re.search(rf"as\s+({_ID})", clause):
            binds[alias.group(1)] = ""
        return binds
    named = re.search(r"\{([^}]*)\}", clause)
    default = clause.split("{", 1)[0].strip().rstrip(",").strip()
    if default and re.fullmatch(_ID, default):
        binds[default] = "default"
    for item in named.group(1).split(",") if named else []:
        parts = item.replace("type ", "").split(" as ")
        name, local = parts[0].strip(), parts[-1].strip()
        if name and re.fullmatch(_ID, local):
            binds[local] = name
    return binds


def _uses(text: str, names: set[str]) -> list[list[str]]:
    if not names:
        return []
    alternation = "|".join(sorted(map(re.escape, names), key=len, reverse=True))
    pattern = re.compile(
        rf"(?:\bnew\s+|<)({alternation})(?=[\s/>(])"  # `new Name`, JSX `<Name`
        rf"|(?<!function )(?<![\w$.])({alternation})\s*\("  # `name(`, not its declaration
    )
    seen = dict.fromkeys(m.group(1) or m.group(2) for m in pattern.finditer(text))
    return [["", name] for name in seen]


def js_facts(text: str) -> dict[str, Any]:
    facts: dict[str, Any] = {"symbols": [], "imports": [], "calls": [], "bases": [], "main": False}
    for match in _JS_FROM.finditer(text):
        line = text.count("\n", 0, match.start()) + 1
        binds = _js_binds(match.group(1))
        facts["imports"].append({"spec": match.group(2), "binds": binds, "line": line})
    for match in _JS_BARE.finditer(text):
        line = text.count("\n", 0, match.start()) + 1
        facts["imports"].append(
            {"spec": match.group(1) or match.group(2), "binds": {}, "line": line}
        )
    for number, line in enumerate(text.splitlines(), start=1):
        for pattern, kind in _JS_DECLS:
            if match := pattern.match(line):
                facts["symbols"].append([match.group(1), kind, number])
                if kind == "class" and match.group(2):
                    facts["bases"].append([match.group(1), match.group(2)])
                break
    bound = {b for i in facts["imports"] for b in i["binds"]}
    local = {s[0] for s in facts["symbols"]}
    facts["calls"] = _uses(re.sub(_JS_FROM, "", text), bound | local)
    return facts


def go_facts(text: str) -> dict[str, Any]:
    facts: dict[str, Any] = {"symbols": [], "imports": [], "calls": [], "bases": [], "main": False}
    block = re.search(r"^import\s*\((.*?)^\)", text, re.MULTILINE | re.DOTALL)
    single = re.findall(r"^import\s+(?:[\w.]+\s+)?\"[^\"]+\"", text, re.MULTILINE)
    for chunk in [block.group(1) if block else "", *single]:
        for match in _GO_IMPORT.finditer(chunk):
            facts["imports"].append({"spec": match.group(2), "binds": {}, "line": 1})
    package_main = re.search(r"^package\s+main\b", text, re.MULTILINE) is not None
    for number, line in enumerate(text.splitlines(), start=1):
        for pattern, kind in _GO_DECLS:
            if match := pattern.match(line):
                name = ".".join(match.groups()) if kind == "method" else match.group(1)
                facts["symbols"].append([name, kind, number])
                facts["main"] = facts["main"] or (package_main and name == "main")
                break
    return facts


def java_facts(text: str) -> dict[str, Any]:
    facts: dict[str, Any] = {"symbols": [], "imports": [], "calls": [], "bases": [], "main": False}
    for match in _JAVA_IMPORT.finditer(text):
        line = text.count("\n", 0, match.start()) + 1
        facts["imports"].append(
            {"spec": match.group(1), "binds": {}, "line": line, "wildcard": bool(match.group(2))}
        )
    for number, line in enumerate(text.splitlines(), start=1):
        if match := _JAVA_DECL.match(line):
            kind, name, base = match.groups()
            facts["symbols"].append([name, "class" if kind == "class" else kind, number])
            if base:
                facts["bases"].append([name, base.rsplit(".", 1)[-1]])
    facts["main"] = "static void main(" in text
    return facts

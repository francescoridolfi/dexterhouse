# SPDX-License-Identifier: AGPL-3.0-or-later
"""One file's facts -> (source id, target id, kind) edges: imports, calls, inherits.

Each import binds local names to a file, a symbol of a file, a module or a package; a call
or a base resolves through the file's own symbols (`self.x` / `this.x` within the class),
then through the longest bound prefix of its dotted name. Unresolved names give no edge.
"""

from collections.abc import Iterator
from typing import Any

from dexterhouse_runner.workspace_mcp.graph.resolve import Resolver, Target

Bound = tuple[str, ...]  # ("file", path) | ("sym", path, name) | ("module", dir) | ("ext", n)
Edge = tuple[str, str, str]


def _target_id(target: Target) -> str:
    kind, value = target
    return {"file": "file:", "module": "module:", "ext": "ext:"}[kind] + value


def _python_binds(imp: dict[str, Any], path: str, resolver: Resolver) -> Iterator[tuple]:
    spec, level = imp["spec"], imp.get("level", 0)
    if not imp["names"]:
        target = resolver.python(spec, level, path)
        for local in imp["binds"]:
            yield local, target, target
        return
    base = resolver.python(spec, level, path)
    for local, name in imp["binds"].items():
        sub = resolver.python(f"{spec}.{name}" if spec else name, level, path)
        if sub is not None and sub[0] == "file":
            yield local, sub, sub
        elif base is not None and base[0] == "file":
            yield local, ("sym", base[1], name), base
        else:
            yield local, base, base


def _binds(lang: str, imp: dict[str, Any], path: str, resolver: Resolver) -> Iterator[tuple]:
    """(local name or None, bound target, imported target) for one import."""
    if lang == "python":
        yield from _python_binds(imp, path, resolver)
        return
    if lang == "go":
        target = resolver.go(imp["spec"])
    elif lang == "java":
        target = resolver.java(imp["spec"], imp.get("wildcard", False), path)
        if target is not None and target[0] == "file":
            name = imp["spec"].rsplit(".", 1)[-1]
            yield name, ("sym", target[1], name), target
            return
    else:
        target = resolver.javascript(imp["spec"], path)
    yield None, None, target
    if target is None or target[0] != "file":
        return
    for local, name in imp["binds"].items():
        yield local, ("sym", target[1], local if name in ("", "default") else name), target
        if name == "":
            yield local, target, target


def link_file(
    path: str, lang: str, facts: dict[str, Any], resolver: Resolver, symbols: dict[str, dict]
) -> Iterator[Edge]:
    own = f"file:{path}"
    local = symbols[path]
    table: dict[str, Bound] = {}
    for imp in facts["imports"]:
        for name, bound, imported in _binds(lang, imp, path, resolver):
            if imported is not None:
                yield own, _target_id(imported), "imports"
            if name is not None and bound is not None:
                table[name] = bound

    def method(cls: str, name: str, owner: dict[str, str], depth: int) -> str | None:
        """`cls.name`, else inherited from a base found in this file (two levels)."""
        if (found := owner.get(f"{cls}.{name}")) is not None or depth > 1 or owner is not local:
            return found
        for sub, base in facts["bases"]:
            sid = resolve(base, "") if sub == cls else None
            if sid is not None:
                path_, qual = sid[4:].split("::", 1)
                if (hit := method(qual, name, symbols.get(path_, {}), depth + 1)) is not None:
                    return hit
        return None

    def resolve(expr: str, caller: str) -> str | None:
        parts = expr.split(".")
        if parts[0] in ("self", "cls", "this") and len(parts) == 2 and "." in caller:
            return method(caller.rsplit(".", 1)[0], parts[1], local, 0)
        for i in range(len(parts), 0, -1):
            if (key := ".".join(parts[:i])) in local:
                return local[key]
            bound = table.get(key)
            if bound is None:
                continue
            rest = parts[i:]
            if bound[0] == "sym":
                found = symbols.get(bound[1], {})
                return found.get(".".join([bound[2], *rest])) or found.get(bound[2])
            if bound[0] == "file" and rest:
                found = symbols.get(bound[1], {})
                return found.get(".".join(rest)) or found.get(rest[0])
            return None
        return None

    for caller, callee in facts["calls"]:
        if (target := resolve(callee, caller)) is not None:
            yield local.get(caller, own) if caller else own, target, "calls"
    for cls, base in facts["bases"]:
        if (target := resolve(base, "")) is not None and cls in local:
            yield local[cls], target, "inherits"

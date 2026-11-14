# SPDX-License-Identifier: AGPL-3.0-or-later
"""Import specifiers -> workspace files, directories (`module`) or external packages.

A target is `("file", path)`, `("module", dir)`, `("ext", name)` or None (standard library,
Node built-ins, unresolved relative imports). Python and Java resolve by dotted suffix,
preferring the candidate closest to the importer; JS/TS by relative path with the usual
extensions and `index` files (`@/` and `~/` are read as `src/`); Go by the `go.mod` module.
"""

import posixpath
import sys
from collections import defaultdict

Target = tuple[str, str]
_STDLIB = frozenset(sys.stdlib_module_names)
_JS_EXTS = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".mts", ".cts")
_NODE_BUILTINS = frozenset(
    "assert buffer child_process crypto events fs http https net os path process querystring "
    "readline stream string_decoder timers tls url util worker_threads zlib".split()
)


class Resolver:
    def __init__(self, files: dict[str, str], go_modules: dict[str, str]) -> None:
        self.files = files  # path -> language
        self.dirs = {posixpath.dirname(p) for p in files}
        self.go_modules = go_modules  # dir of go.mod -> module path
        self.dotted: dict[str, list[str]] = defaultdict(list)
        for path, lang in sorted(files.items()):
            if lang in ("python", "java"):
                parts = posixpath.splitext(path)[0].split("/")
                if parts[-1] == "__init__":
                    parts = parts[:-1]
                for i in range(len(parts)):
                    self.dotted[".".join(parts[i:])].append(path)

    def _closest(self, candidates: list[str], importer: str) -> str:
        def score(path: str) -> tuple[int, int]:
            common = posixpath.commonpath([path, importer]) if "/" in path else ""
            return (-len(common.split("/")) if common else 0, len(path))

        return min(candidates, key=score)

    def python(self, spec: str, level: int, importer: str) -> Target | None:
        if level:
            base = posixpath.dirname(importer).split("/") if "/" in importer else []
            base = base[: len(base) - (level - 1)] if level > 1 else base
            stem = "/".join([*base, *spec.split(".")] if spec else base)
            for candidate in (f"{stem}.py", f"{stem}.pyi", f"{stem}/__init__.py"):
                if candidate.lstrip("/") in self.files:
                    return ("file", candidate.lstrip("/"))
            return None
        top = spec.split(".")[0]
        if top in _STDLIB:
            return None
        candidates = self.dotted.get(spec)
        if candidates:
            return ("file", self._closest(candidates, importer))
        return ("ext", top) if top else None

    def javascript(self, spec: str, importer: str) -> Target | None:
        if spec.startswith(("@/", "~/")):
            base = posixpath.normpath("src/" + spec[2:])
        elif spec.startswith("."):
            base = posixpath.normpath(posixpath.join(posixpath.dirname(importer), spec))
        else:
            name = spec.removeprefix("node:")
            if spec.startswith("node:") or name.split("/")[0] in _NODE_BUILTINS:
                return None
            parts = name.split("/")
            return ("ext", "/".join(parts[:2]) if name.startswith("@") else parts[0])
        stem, ext = posixpath.splitext(base)
        stem = stem if ext in (".js", ".jsx", ".mjs", ".cjs") else base  # `./a.js` -> a.ts
        candidates = [base, *(stem + e for e in _JS_EXTS), *(f"{base}/index{e}" for e in _JS_EXTS)]
        return next((("file", c) for c in candidates if c in self.files), None)

    def go(self, spec: str) -> Target | None:
        for folder, module in sorted(self.go_modules.items(), key=lambda m: -len(m[1])):
            if spec == module or spec.startswith(module + "/"):
                rest = spec[len(module) :].lstrip("/")
                target = posixpath.join(folder, rest) if folder else rest
                return ("module", target) if target in self.dirs else None
        first = spec.split("/")[0]
        return ("ext", "/".join(spec.split("/")[:3])) if "." in first else None

    def java(self, spec: str, wildcard: bool, importer: str) -> Target | None:
        if wildcard:
            dirs = [d for d in self.dirs if d.replace("/", ".").endswith(spec)]
            return ("module", self._closest(dirs, importer)) if dirs else None
        candidates = self.dotted.get(spec)
        if candidates:
            return ("file", self._closest(candidates, importer))
        if spec.startswith(("java.", "javax.", "jdk.", "kotlin.")):
            return None
        return ("ext", ".".join(spec.split(".")[:2]))

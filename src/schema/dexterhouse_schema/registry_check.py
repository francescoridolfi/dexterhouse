# SPDX-License-Identifier: AGPL-3.0-or-later
"""Registry CI checks (infra/registry_ci.md): archive hash, prompt scan, entry coherence.

`archive_sha256` is the hash the core installer verifies: the sha256 of
`git archive --format=tar <ref>`. `check_entry` compares a `packages/<name>.json` with the
package checked out at one of its versions; `scan_prompts` looks for the forbidden
patterns of :mod:`dexterhouse_schema.prompts` in prompts and skills.
"""

import hashlib
import re
import shutil
import subprocess  # nosec B404: fixed argv, no shell, only `git archive`
from pathlib import Path

from packaging.specifiers import InvalidSpecifier, SpecifierSet

from dexterhouse_schema.manifest import Manifest
from dexterhouse_schema.package import MANIFEST_FILE, validate_package
from dexterhouse_schema.prompts import scan_text
from dexterhouse_schema.registry import RegistryPackage
from dexterhouse_schema.tool import LAUNCHERS, RISK_ORDER, Tool, check_command

GIT_TIMEOUT_S = 120
LICENSE_FILES = ("LICENSE", "LICENSE.md", "LICENSE.txt", "COPYING")
#: Folders whose text `scan_prompts` reads (agent prompts and skills).
SCANNED_DIRS = ("prompts", "skills")
#: OSI-approved SPDX ids accepted by the registry; ask a maintainer to add another one.
OSI_LICENSES: frozenset[str] = frozenset(
    {
        "0BSD", "AFL-3.0", "AGPL-3.0-only", "AGPL-3.0-or-later", "Apache-2.0", "Artistic-2.0",
        "BSD-2-Clause", "BSD-3-Clause", "BSL-1.0", "CC0-1.0", "CDDL-1.0", "ECL-2.0", "EPL-1.0",
        "EPL-2.0", "EUPL-1.2", "GPL-2.0-only", "GPL-2.0-or-later", "GPL-3.0-only",
        "GPL-3.0-or-later", "ISC", "LGPL-2.1-only", "LGPL-2.1-or-later", "LGPL-3.0-only",
        "LGPL-3.0-or-later", "MIT", "MIT-0", "MPL-2.0", "MS-PL", "NCSA", "OSL-3.0",
        "PostgreSQL", "UPL-1.0", "Unlicense", "Zlib",
    }
)  # fmt: skip
_SPDX_ID_RE = re.compile(r"[A-Za-z0-9.+-]+")
_SPDX_OPERATORS = frozenset({"AND", "OR", "WITH"})


class HashError(Exception):
    """The archive cannot be produced (not a git repository, unknown ref, no git)."""


def archive_sha256(path: str | Path, ref: str = "HEAD") -> str:
    """sha256 of `git archive --format=tar <ref>` in the repository at `path`."""
    git = shutil.which("git")
    if git is None:
        raise HashError("git is not installed")
    if ref.startswith("-"):
        raise HashError(f"invalid ref {ref!r}")
    try:
        result = subprocess.run(  # noqa: S603  # nosec B603: argv list, ref checked above
            [git, "-C", str(path), "archive", "--format=tar", ref],
            capture_output=True,
            timeout=GIT_TIMEOUT_S,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise HashError(f"git archive timed out after {GIT_TIMEOUT_S}s") from exc
    if result.returncode != 0:
        detail = result.stderr.decode(errors="replace").strip().splitlines()
        raise HashError(f"git archive failed: {detail[-1] if detail else result.returncode}")
    return hashlib.sha256(result.stdout).hexdigest()


def scan_prompts(root: str | Path) -> list[str]:
    """`<path>:<line>: <pattern id>: <excerpt>` for each forbidden pattern in prompts/skills."""
    base = Path(root)
    hits: list[str] = []
    for folder in SCANNED_DIRS:
        for path in sorted((base / folder).rglob("*")):
            if not path.is_file() or path.is_symlink():
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue  # binary support files: `validate` reports what is not allowed
            rel = path.relative_to(base).as_posix()
            hits += [f"{rel}:{m.line}: {m.pattern_id}: {m.excerpt!r}" for m in scan_text(text)]
    return hits


def license_errors(expression: str) -> list[str]:
    """Every SPDX id in `expression` must be OSI-approved (`WITH` exceptions excepted)."""
    tokens = _SPDX_ID_RE.findall(expression)
    ids = [
        t
        for i, t in enumerate(tokens)
        if t not in _SPDX_OPERATORS and not (i and tokens[i - 1] == "WITH")
    ]
    return [f"license {i!r} is not an OSI-approved SPDX id" for i in ids if i not in OSI_LICENSES]


def _same_range(a: str, b: str) -> bool:
    try:
        return SpecifierSet(a) == SpecifierSet(b)
    except InvalidSpecifier:
        return False


def check_entry(entry: RegistryPackage, root: str | Path, version: str | None = None) -> list[str]:
    """Coherence between a registry entry and the package checked out at `version`.

    `version` defaults to the latest one in the entry. Schema errors of the package are
    reported by `validate`; here a missing or invalid manifest is a single error.
    """
    base = Path(root)
    wanted = version or entry.versions[-1].version
    published = next((v for v in entry.versions if v.version == wanted), None)
    if published is None:
        return [f"version {wanted} is not listed in {entry.name}.json"]
    report = validate_package(base)
    manifest = report.models.get(MANIFEST_FILE)
    if not isinstance(manifest, Manifest):
        return [f"{MANIFEST_FILE} is missing or invalid: run `dexterhouse-schema validate`"]
    errors = [
        f"{field} is {got!r} in {MANIFEST_FILE}, {want!r} in the registry"
        for field, got, want in (
            ("name", manifest.name, entry.name),
            ("kind", manifest.kind, entry.kind),
            ("version", manifest.version, published.version),
        )
        if got != want
    ]
    if not _same_range(manifest.compat.core, published.compat_core):
        errors.append(
            f"compat.core is {manifest.compat.core!r}, compat_core {published.compat_core!r}"
        )
    if (manifest.author.github or "").lower() != entry.author_github.lower():
        errors.append(f"author.github must be {entry.author_github!r} (author_github)")
    if published is entry.versions[-1]:
        if entry.description != manifest.description:
            errors.append("description must equal the manifest description")
        if entry.tags != manifest.tags:
            errors.append("tags must equal the manifest tags")
    errors += license_errors(manifest.license)
    if not any((base / name).is_file() for name in LICENSE_FILES):
        errors.append(f"no license file ({', '.join(LICENSE_FILES)}) in the package")
    tool = report.models.get("tool.yaml")
    if isinstance(tool, Tool):
        errors += _tool_errors(entry, tool)
    return errors


def _tool_errors(entry: RegistryPackage, tool: Tool) -> list[str]:
    """Registry rules on top of the schema: allow-listed launcher, pinned, declared risk."""
    errors: list[str] = []
    if tool.command:
        if tool.command[0] not in LAUNCHERS:
            errors.append(
                f"command[0] {tool.command[0]!r} must be one of {', '.join(sorted(LAUNCHERS))}"
            )
        else:
            try:
                check_command(tool.command)
            except ValueError as exc:
                errors.append(str(exc))
    if RISK_ORDER[entry.risk] < RISK_ORDER[tool.max_risk]:
        errors.append(f"risk is {entry.risk!r}, the highest permission risk is {tool.max_risk!r}")
    return errors

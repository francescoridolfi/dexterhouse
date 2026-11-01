# SPDX-License-Identifier: AGPL-3.0-or-later
"""Marketplace client: search, details and reachability, for the REST proxy and the tools.

In 1.0 the only source is the registry index (`index.get_index()`, CD-041): `source` is
`index` (fresh) or `cache` (the last good copy: the registry is unreachable now), or
`unreachable` when there is neither. Ratings, installs and reviews belong to the future
marketplace site (`settings.MARKETPLACE_URL`, read but unused): they are None / empty until
a site source (`source: api`) is tried before :func:`_snapshot` by `search` and `details`.

Texts from packages are wrapped as untrusted (`untrusted.wrap`) for agents; the REST proxy
asks for them unwrapped (`mark_untrusted=False`). Search results are cached
for `MARKETPLACE_SEARCH_TTL_S`, package files for `MARKETPLACE_DETAILS_TTL_S` (Redis).
"""

import re
import uuid
from typing import Any

import structlog
import yaml
from django.conf import settings

from dexterhouse.apps.packages.services import catalog, repo_files, shared_cache, untrusted
from dexterhouse.apps.packages.services import index as registry
from dexterhouse_schema.registry import IndexEntry

logger = structlog.get_logger(__name__)
MAX_LIMIT = 25
README_BYTES = 16 * 1024
DEFINITION_FILE = {"agent": "agent.yaml", "tool": "tool.yaml", "process": "process.yaml"}
_TOKEN = re.compile(r"[a-z0-9]+")


class MarketplaceUnavailableError(Exception):
    """No registry is configured, or it is unreachable and there is no saved copy."""


class PackageNotFoundError(Exception):
    """The name is not in the registry index."""


def site_configured() -> bool:
    """The marketplace site API (1.x): configured is reported, never queried in 1.0."""
    return bool(settings.MARKETPLACE_URL)


def _snapshot() -> registry.IndexSnapshot:
    try:
        snapshot = registry.get_index()
    except registry.IndexUnavailableError as exc:
        raise MarketplaceUnavailableError(str(exc)) from exc
    if snapshot is None:
        raise MarketplaceUnavailableError("no registry configured (REGISTRY_INDEX_URL)")
    return snapshot


def status() -> dict[str, Any]:
    """Reachability of the registry (and whether a site is configured)."""
    registry_info: dict[str, Any] = {
        "configured": registry.configured(),
        "url": settings.REGISTRY_INDEX_URL or None,
    }
    source = None
    try:
        snapshot = _snapshot()
    except MarketplaceUnavailableError as exc:
        registry_info["error"] = str(exc)
    else:
        source = snapshot.source
        registry_info["packages"] = len(snapshot.index.packages)
        registry_info["generated_at"] = snapshot.index.generated_at.isoformat()
    state = {"index": "reachable", "cache": "degraded"}.get(source or "", "unreachable")
    return {
        "status": state,
        "source": source or "unreachable",
        "registry": registry_info,
        "site": {"configured": site_configured(), "used": False},
    }


def _marker(mark: bool) -> Any:
    return untrusted.wrap if mark else (lambda text: text)


def _summary(entry: IndexEntry, mark: bool = True) -> dict[str, Any]:
    compatible = registry.pick_version(entry)
    return {
        "name": entry.name,
        "kind": entry.kind,
        "description": _marker(mark)(entry.description),
        "tags": list(entry.tags),
        "author": entry.author_github,
        "verified": entry.verified,
        "rating": None,
        "installs": None,
        "latest": entry.latest,
        "compatible_version": compatible.version if compatible else None,
        "compat_ok": compatible is not None,
        "risk": entry.risk,
    }


def _score(entry: IndexEntry, tokens: set[str]) -> int:
    if not tokens:
        return 1
    name = set(_TOKEN.findall(entry.name))
    tags = {t for tag in entry.tags for t in _TOKEN.findall(tag.lower())}
    words = set(_TOKEN.findall(entry.description.lower()))
    return sum(3 * (t in name) + 2 * (t in tags) + (t in words) for t in tokens)


def search(
    query: str = "",
    kind: str | None = None,
    tags: list[str] | None = None,
    verified_only: bool = False,
    min_rating: float | None = None,
    limit: int = 10,
    *,
    mark_untrusted: bool = True,
) -> dict[str, Any]:
    """Packages matching the words of `query` (name, tags, description), best first."""
    limit = max(1, min(int(limit), MAX_LIMIT))
    wanted_tags = sorted({t.lower() for t in tags or []})
    cache_key = shared_cache.key(
        "search",
        settings.REGISTRY_INDEX_URL,
        query,
        kind,
        wanted_tags,
        verified_only,
        limit,
        mark_untrusted,
    )
    result = shared_cache.get(cache_key)
    if result is None:
        try:
            snapshot = _snapshot()
        except MarketplaceUnavailableError as exc:
            return {"source": "unreachable", "results": [], "total": 0, "error": str(exc)}
        tokens = set(_TOKEN.findall(query.lower()))
        scored = [
            (score, entry)
            for entry in snapshot.index.packages
            if (kind is None or entry.kind == kind)
            and (not verified_only or entry.verified)
            and set(wanted_tags) <= {t.lower() for t in entry.tags}
            and (score := _score(entry, tokens)) > 0
        ]
        scored.sort(key=lambda s: (-s[0], not s[1].verified, s[1].name))
        result = {
            "source": snapshot.source,
            "results": [_summary(entry, mark_untrusted) for _, entry in scored[:limit]],
            "total": len(scored),
        }
        if snapshot.source == "index":
            shared_cache.put(cache_key, result, settings.MARKETPLACE_SEARCH_TTL_S)
    if min_rating is not None:
        result["notes"] = ["min_rating ignored: the registry index has no ratings (1.0)"]
    return result


def _yaml(text: str | None, warnings: list[str], name: str) -> dict[str, Any]:
    if not text:
        return {}
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        warnings.append(f"{name}: invalid YAML ({exc.__class__.__name__})")
        return {}
    return data if isinstance(data, dict) else {}


def _permissions(
    kind: str, definition: dict[str, Any], organization_id: uuid.UUID | None, mark: bool
) -> list[dict[str, Any]]:
    """A tool's own permissions, or the tools an agent requires with their installed risk."""
    if kind == "tool":
        return [
            {
                "id": str(p.get("id", "")),
                "risk": p.get("risk"),
                "description": _marker(mark)(str(p.get("description") or "")),
            }
            for p in definition.get("permissions") or []
            if isinstance(p, dict)
        ]
    if kind != "agent":
        return []
    known = {
        p["id"]: p
        for v in catalog.enabled_versions("tool", organization_id, ensure=False)
        for p in v.permissions
    }
    permissions = []
    for tool_id in definition.get("tools") or []:
        installed = known.get(str(tool_id))
        permissions.append(
            {
                "id": str(tool_id),
                "risk": installed["risk"] if installed else None,
                "available": installed is not None,
            }
        )
    return permissions


def _role_warnings(role: str, name: str, organization_id: uuid.UUID | None) -> list[str]:
    for version in catalog.enabled_versions("agent", organization_id, ensure=False):
        if version.definition.get("role") == role and version.package.name != name:
            return [f"role {role} is already provided by {version.package.name}"]
    return []


def details(
    name: str, organization_id: uuid.UUID | None = None, *, mark_untrusted: bool = True
) -> dict[str, Any]:
    """A package's index entry, README, definition summary and requested permissions."""
    snapshot = _snapshot()
    entry = snapshot.get(name)
    if entry is None:
        raise PackageNotFoundError(f"{name} is not in the registry index")
    data = _summary(entry, mark_untrusted)
    chosen = registry.pick_version(entry) or entry.versions[-1]
    warnings: list[str] = []
    try:
        names = ["README.md", "dexterhouse.yaml", DEFINITION_FILE[entry.kind]]
        files = repo_files.read(entry.repo, chosen.ref, names)
        files_status = "ok"
    except repo_files.RepoFilesUnavailableError as exc:
        files, files_status = {}, "unavailable"
        warnings.append(f"package files unavailable: {exc}")
    readme = files.get("README.md") or ""
    manifest = _yaml(files.get("dexterhouse.yaml"), warnings, "dexterhouse.yaml")
    definition = _yaml(files.get(DEFINITION_FILE[entry.kind]), warnings, "definition")
    flags = sorted(set(untrusted.flags(readme)) | set(untrusted.flags(entry.description)))
    if flags:
        logger.warning("marketplace.package_flagged", package=name, flags=flags)
    office = definition.get("office") if isinstance(definition.get("office"), dict) else {}
    role = str(definition.get("role") or "") or None
    if role:
        warnings += _role_warnings(role, name, organization_id)
    installed = catalog.find_version(entry.kind, name, organization_id)
    data.update(
        {
            "source": snapshot.source,
            "repo": entry.repo,
            "version": chosen.version,
            "ref": chosen.ref,
            "versions": [
                {"version": v.version, "compat_ok": registry.compatible(v.compat_core)}
                for v in entry.versions
            ],
            "license": manifest.get("license"),
            "role": role,
            "room": office.get("room"),
            "skills": [str(s) for s in definition.get("skills") or []],
            "permissions": _permissions(entry.kind, definition, organization_id, mark_untrusted),
            "readme": _marker(mark_untrusted)(readme[:README_BYTES]),
            "readme_truncated": len(readme) > README_BYTES,
            "reviews": [],
            "installed_version": installed.version if installed else None,
            "files": files_status,
            "flags": flags,
            "warnings": warnings,
        }
    )
    return data


def entry(name: str) -> IndexEntry | None:
    """The index entry of `name` (for `packages.install` and the proposals), if reachable."""
    try:
        return _snapshot().get(name)
    except MarketplaceUnavailableError:
        return None

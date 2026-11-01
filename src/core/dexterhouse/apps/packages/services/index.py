# SPDX-License-Identifier: AGPL-3.0-or-later
"""Registry index client: `REGISTRY_INDEX_URL` (`index.json`, registry_index.md).

The index is the second source the installer trusts (threat model T17): the sha256 of a
version comes from it, never from the package. It is fetched over HTTPS (or `file://`, for
private registries mounted on disk and tests), validated with `dexterhouse-schema`, kept
in memory for `REGISTRY_INDEX_TTL_S` and saved as the last good copy in
`PACKAGES_DIR/.registry/index.json`, used when the registry is unreachable.
"""

import json
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import url2pathname

import httpx2
import structlog
from django.conf import settings
from packaging.specifiers import InvalidSpecifier, SpecifierSet
from pydantic import ValidationError

from dexterhouse import __version__
from dexterhouse_schema import RegistryIndex
from dexterhouse_schema.registry import IndexEntry, IndexVersion
from dexterhouse_schema.semver import SemanticVersion

logger = structlog.get_logger(__name__)
FETCH_TIMEOUT_S = 10.0


class IndexUnavailableError(Exception):
    """The index cannot be fetched or is invalid, and there is no saved copy."""


@dataclass(frozen=True)
class IndexSnapshot:
    index: RegistryIndex
    source: str  # "index" (fresh) or "cache" (last good copy)

    def get(self, name: str) -> IndexEntry | None:
        return next((p for p in self.index.packages if p.name == name), None)


_memory: dict[str, tuple[float, IndexSnapshot]] = {}


def configured() -> bool:
    return bool(settings.REGISTRY_INDEX_URL)


def _cache_file() -> Path:
    return Path(settings.PACKAGES_DIR) / ".registry" / "index.json"


def _download(url: str) -> bytes:
    parts = urlsplit(url)
    if parts.scheme == "file":
        return Path(url2pathname(parts.path)).read_bytes()
    if parts.scheme != "https":
        raise IndexUnavailableError(f"REGISTRY_INDEX_URL must be https:// or file://, not {url}")
    response = httpx2.get(url, timeout=FETCH_TIMEOUT_S, follow_redirects=True)
    response.raise_for_status()
    return response.content


def get_index(*, refresh: bool = False) -> IndexSnapshot | None:
    """The registry index, or None when no registry is configured (offline installs).

    Raises :class:`IndexUnavailableError` when it cannot be fetched and no copy is saved.
    """
    url = settings.REGISTRY_INDEX_URL
    if not url:
        return None
    cached = _memory.get(url)
    if cached and not refresh and time.monotonic() - cached[0] < settings.REGISTRY_INDEX_TTL_S:
        return cached[1]
    try:
        raw = _download(url)
        index = RegistryIndex.model_validate(json.loads(raw))
    except (OSError, httpx2.HTTPError, ValueError, ValidationError, IndexUnavailableError) as exc:
        logger.warning("packages.index_unavailable", url=url, error=str(exc))
        return _saved_copy(url, exc)
    snapshot = IndexSnapshot(index, "index")
    _memory[url] = (time.monotonic(), snapshot)
    try:
        _cache_file().parent.mkdir(parents=True, exist_ok=True)
        _cache_file().write_bytes(raw)
    except OSError as exc:
        logger.warning("packages.index_cache_write_failed", error=str(exc))
    return snapshot


def _saved_copy(url: str, cause: Exception) -> IndexSnapshot:
    try:
        index = RegistryIndex.model_validate(json.loads(_cache_file().read_bytes()))
    except (OSError, ValueError, ValidationError) as exc:
        raise IndexUnavailableError(f"registry index unavailable: {cause}") from exc
    snapshot = IndexSnapshot(index, "cache")
    _memory[url] = (time.monotonic(), snapshot)
    return snapshot


def clear_cache() -> None:
    _memory.clear()


def compatible(compat_core: str, core_version: str = __version__) -> bool:
    """Whether `core_version` is in the PEP 440 range `compat_core` (pre-releases included)."""
    try:
        return SpecifierSet(compat_core).contains(core_version, prereleases=True)
    except InvalidSpecifier:
        return False


def pick_version(entry: IndexEntry, version: str | None = None) -> IndexVersion | None:
    """`version` from the entry, or the highest one compatible with this core."""
    if version:
        return next((v for v in entry.versions if v.version == version), None)
    candidates = [v for v in entry.versions if compatible(v.compat_core)]
    return max(candidates, key=lambda v: SemanticVersion(v.version), default=None)


def same_repo(a: str, b: str) -> bool:
    """Compare repository URLs ignoring scheme case, a trailing `/` or `.git`."""

    def norm(url: str) -> str:
        url = url.strip().rstrip("/").removesuffix(".git")
        parts = urlsplit(url)
        return f"{parts.netloc.lower()}{parts.path}" if parts.netloc else url

    return norm(a) == norm(b)

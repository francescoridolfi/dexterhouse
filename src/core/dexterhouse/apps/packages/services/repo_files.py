# SPDX-License-Identifier: AGPL-3.0-or-later
"""Files of a package at a tag, read from its repository without cloning it.

The URL comes from `settings.MARKETPLACE_RAW_URL` (`{host}`, `{path}`, `{ref}`, `{file}`),
or, when that is empty, from raw.githubusercontent.com for GitHub repositories only: the
client talks to no host but the registry and the repositories of the packages. A template
may be `file://` (registries mirrored on disk, tests). Files are cached for
`MARKETPLACE_DETAILS_TTL_S`; a missing file is cached as missing.
"""

from pathlib import Path
from urllib.parse import quote, urlsplit
from urllib.request import url2pathname

import httpx2
import structlog
from django.conf import settings

from dexterhouse.apps.packages.services import shared_cache

logger = structlog.get_logger(__name__)
GITHUB_RAW = "https://raw.githubusercontent.com/{path}/{ref}/{file}"
FETCH_TIMEOUT_S = 10.0
MAX_FILE_BYTES = 256 * 1024


class RepoFilesUnavailableError(Exception):
    """The repository host is not supported or did not answer."""


def file_url(repo: str, ref: str, name: str) -> str:
    parts = urlsplit(repo)
    path = parts.path.strip("/").removesuffix(".git")
    template = settings.MARKETPLACE_RAW_URL
    if not template:
        if parts.hostname != "github.com":
            raise RepoFilesUnavailableError(
                f"{parts.hostname}: only GitHub repositories without MARKETPLACE_RAW_URL"
            )
        template = GITHUB_RAW
    return template.format(
        host=parts.hostname or "", path=path, ref=quote(ref, safe=""), file=quote(name)
    )


def _download(url: str) -> bytes | None:
    """The file, or None when the repository has no such file (404)."""
    parts = urlsplit(url)
    if parts.scheme == "file":
        path = Path(url2pathname(parts.path))
        return path.read_bytes()[:MAX_FILE_BYTES] if path.is_file() else None
    if parts.scheme != "https":
        raise RepoFilesUnavailableError(f"package files must be https:// or file://, not {url}")
    response = httpx2.get(url, timeout=FETCH_TIMEOUT_S, follow_redirects=False)
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return response.content[:MAX_FILE_BYTES]


def read(repo: str, ref: str, names: list[str]) -> dict[str, str | None]:
    """`{file: text or None}` of the package at `ref`; raises when the host cannot be read."""
    cache_key = shared_cache.key("files", repo, ref, sorted(names))
    cached = shared_cache.get(cache_key)
    if cached is not None:
        return dict(cached)
    files: dict[str, str | None] = {}
    for name in names:
        url = file_url(repo, ref, name)
        try:
            data = _download(url)
        except (OSError, httpx2.HTTPError) as exc:
            logger.warning("marketplace.files_unavailable", url=url, error=str(exc))
            raise RepoFilesUnavailableError(f"{url}: {exc}") from exc
        files[name] = data.decode("utf-8", errors="replace") if data is not None else None
    shared_cache.put(cache_key, files, settings.MARKETPLACE_DETAILS_TTL_S)
    return files

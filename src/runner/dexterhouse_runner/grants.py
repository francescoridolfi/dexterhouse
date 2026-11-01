# SPDX-License-Identifier: AGPL-3.0-or-later
"""Redeem a one-time `SecretGrant` at the core (CD-020): the only way the runner gets a token.

`GET {CORE_URL}/internal/secrets/{grant_id}` with `X-Runner-Key`; the core answers once
(`{"value": …}`) and deletes the grant. The value is returned to the caller and never logged.
"""

import json
import urllib.error
import urllib.request
import uuid

from dexterhouse_runner.config import RunnerSettings
from dexterhouse_runner.docker_manager import RunnerError

TIMEOUT_S = 10


def redeem(grant_id: uuid.UUID, settings: RunnerSettings) -> str:
    url = f"{settings.CORE_URL.rstrip('/')}/internal/secrets/{grant_id}"
    if not url.startswith(("http://", "https://")):
        raise RunnerError("auth", "CORE_URL must be http(s)")
    key = settings.runner_key()
    if not key:
        raise RunnerError("auth", "RUNNER_KEY is not configured")
    request = urllib.request.Request(url, headers={"X-Runner-Key": key})  # noqa: S310
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:  # noqa: S310  # nosec B310 - scheme checked
            value = json.loads(response.read())["value"]
    except urllib.error.HTTPError as exc:
        raise RunnerError("auth", f"the grant could not be redeemed (HTTP {exc.code})") from exc
    except (urllib.error.URLError, TimeoutError, KeyError, ValueError) as exc:
        raise RunnerError("network", f"the core is unreachable for the grant: {exc}") from exc
    if not isinstance(value, str) or not value:
        raise RunnerError("auth", "the grant carries no token")
    return value

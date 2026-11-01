# SPDX-License-Identifier: AGPL-3.0-or-later
"""Short-lived turn tokens for the MCP bridge (CD-025): HS256 JWT, 10 minutes.

Django-free so the bridge process can verify a token without loading settings.
"""

import hashlib
import hmac
import time
import uuid
from typing import Any

import jwt

AUDIENCE = "dexterhouse-mcp-bridge"
TTL_S = 600


def bridge_key(secret_key: str) -> str:
    """Key derived from the Django secret: a leaked bridge key cannot sign anything else."""
    return hmac.new(secret_key.encode(), AUDIENCE.encode(), hashlib.sha256).hexdigest()


def issue_turn_token(
    *, key: str, turn_id: uuid.UUID | str | None, tools_sha256: str, ttl_s: int = TTL_S
) -> str:
    now = int(time.time())
    claims = {
        "aud": AUDIENCE,
        "sub": str(turn_id or ""),
        "tools": tools_sha256,
        "iat": now,
        "exp": now + ttl_s,
    }
    return jwt.encode(claims, key, algorithm="HS256")


def verify_turn_token(token: str, *, key: str, tools_sha256: str | None = None) -> dict[str, Any]:
    """Claims of a valid token.

    Raises:
        jwt.InvalidTokenError: bad signature, expired, wrong audience or tool list.
    """
    claims = jwt.decode(token, key, algorithms=["HS256"], audience=AUDIENCE)
    if tools_sha256 is not None and not hmac.compare_digest(claims.get("tools", ""), tools_sha256):
        raise jwt.InvalidTokenError("tool list does not match the token")
    return claims

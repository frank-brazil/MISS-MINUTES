"""Minimal authentication boundary for the distributed HTTP layer.

CHUNK 29 only establishes a shared-token boundary.  It deliberately does NOT
build the full permissions/per-actor security framework (that is a later
chunk).  The token is never logged and never serialized into responses or
worker models.
"""

import secrets

from fastapi import HTTPException, Request

AUTH_HEADER = "X-Auth-Token"
# ADD API HERE: MISSMINUTES_AUTH_TOKEN (internal shared secret for master/worker auth)


def build_auth_dependency(config) -> callable:
    """Build a FastAPI dependency enforcing the configured shared token.

    When ``config.auth_token`` is ``None`` authentication is disabled (the
    default bind hosts are then loopback-only).  When set, every guarded
    request must present the matching ``X-Auth-Token`` header.
    """

    token = config.auth_token

    async def require_auth(request: Request) -> None:
        if token is None:
            return
        presented = request.headers.get(AUTH_HEADER)
        if presented is None or not secrets.compare_digest(presented, token):
            raise HTTPException(status_code=401, detail="unauthorized")

    return require_auth


def request_headers(config) -> dict[str, str]:
    """Return headers a transport client attaches for the shared token.

    Never include the token value in any logged or returned payload; callers
    use this only to build the outgoing request.
    """
    if config.auth_token is None:
        return {}
    return {AUTH_HEADER: config.auth_token}

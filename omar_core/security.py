"""Security controls for Omar Core.

Design goals:
- Fail closed if the shared secret is not configured.
- Constant-time API-key comparison.
- No request-body or secret logging.
- Conservative per-process rate limiting as a second line of defense.
"""
from __future__ import annotations

import os
import secrets
import time
from collections import defaultdict, deque
from threading import Lock

from fastapi import Header, HTTPException, Request, status

API_KEY_ENV = "OMAR_API_KEY"
API_KEY_HEADER = "X-Omar-Key"
RATE_LIMIT_PER_MINUTE = int(os.getenv("OMAR_RATE_LIMIT_PER_MINUTE", "60"))

_attempts: dict[str, deque[float]] = defaultdict(deque)
_attempts_lock = Lock()


def require_api_key(x_omar_key: str | None = Header(default=None, alias=API_KEY_HEADER)) -> None:
    expected = os.getenv(API_KEY_ENV)
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Omar security configuration unavailable",
        )
    if not x_omar_key or not secrets.compare_digest(x_omar_key, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")


def enforce_rate_limit(request: Request) -> None:
    """Simple fail-closed per-process limiter.

    This is intentionally conservative and does not replace edge/provider rate
    limiting when Omar scales to multiple machines.
    """
    client = request.client.host if request.client else "unknown"
    now = time.monotonic()
    cutoff = now - 60.0

    with _attempts_lock:
        bucket = _attempts[client]
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        if len(bucket) >= RATE_LIMIT_PER_MINUTE:
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Rate limit exceeded")
        bucket.append(now)

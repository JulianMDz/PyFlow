"""Guards for running the API as a public demo: read-only mode and a rate limit on risk checks."""

import math
import time
from collections import deque

from fastapi import HTTPException, Request, status

from app.core.config import settings


def forbid_in_demo() -> None:
    if settings.DEMO_MODE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This is a read-only demo: run PayFlow locally to create or change data.",
        )


class RateLimiter:
    """Sliding window per key, kept in memory: enough for a single-instance demo.

    With several instances each one would count on its own; a shared store such as
    Redis would be needed then.
    """

    def __init__(self, window_seconds: float = 60.0) -> None:
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = {}

    def retry_after(self, key: str, limit: int, now: float) -> int | None:
        """Record a hit, or return the seconds to wait if the key already reached the limit."""
        hits = self._hits.setdefault(key, deque())
        while hits and hits[0] <= now - self.window:
            hits.popleft()
        if len(hits) >= limit:
            return max(1, math.ceil(hits[0] + self.window - now))
        hits.append(now)
        return None

    def reset(self) -> None:
        self._hits.clear()


risk_limiter = RateLimiter()


def limit_risk_checks(request: Request) -> None:
    limit = settings.RISK_CHECKS_PER_MINUTE
    if limit <= 0:
        return
    client = request.client.host if request.client else "unknown"
    wait = risk_limiter.retry_after(client, limit, time.monotonic())
    if wait is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many risk checks. Try again in {wait} seconds.",
            headers={"Retry-After": str(wait)},
        )

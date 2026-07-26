"""Small, dependency-free, process-local fixed-window rate limiter.

It is intentionally a safety net for the current Railway deployment, not a
replacement for a shared edge/WAF limit in a multi-replica production setup.
"""

from __future__ import annotations

import time
from collections import deque


class RateLimiter:
    def __init__(self) -> None:
        self._attempts: dict[str, deque[float]] = {}

    def allow(self, key: str, limit: int, window_seconds: int, now: float | None = None) -> bool:
        current = time.monotonic() if now is None else now
        attempts = self._attempts.setdefault(key, deque())
        threshold = current - window_seconds
        while attempts and attempts[0] <= threshold:
            attempts.popleft()
        if len(attempts) >= limit:
            return False
        attempts.append(current)
        return True


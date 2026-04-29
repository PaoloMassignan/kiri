from __future__ import annotations

import threading
import time
from collections import deque


class RateLimitExceeded(Exception):
    def __init__(self, retry_after: int) -> None:
        super().__init__(f"rate limit exceeded, retry after {retry_after}s")
        self.retry_after = retry_after


class RateLimiter:
    """Sliding-window rate limiter, per-key, in-memory.

    Args:
        rpm: Maximum requests per minute. 0 disables rate limiting.
    """

    def __init__(self, rpm: int = 0) -> None:
        self._rpm = rpm
        self._buckets: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        return self._rpm > 0

    def check(self, key: str) -> None:
        """Record a request for *key* and raise RateLimitExceeded if over limit.

        Uses a sliding 60-second window. Thread-safe.
        """
        if not self.enabled:
            return

        now = time.monotonic()
        window_start = now - 60.0

        with self._lock:
            bucket = self._buckets.setdefault(key, deque())

            # drop timestamps outside the sliding window
            while bucket and bucket[0] <= window_start:
                bucket.popleft()

            if len(bucket) >= self._rpm:
                # retry_after = seconds until the oldest entry leaves the window
                retry_after = max(1, int(bucket[0] - window_start) + 1)
                raise RateLimitExceeded(retry_after=retry_after)

            bucket.append(now)

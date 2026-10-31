"""Per-IP rate limiting. Counters live in memory, or in Redis when several workers share them."""

from __future__ import annotations

from limits import parse
from limits.storage import storage_from_string
from limits.strategies import FixedWindowRateLimiter


class RateLimiter:
    def __init__(self, storage_uri: str):
        self._limiter = FixedWindowRateLimiter(storage_from_string(storage_uri))

    def allow(self, rate: str, scope: str, ip: str) -> bool:
        """Count this request. False means the limit, such as "30/minute", is used up."""
        return self._limiter.hit(parse(rate), scope, ip)

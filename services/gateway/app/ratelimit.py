"""Fixed-window rate limiting with a Redis counter.

If Redis is down we *fail open* (let requests through and log a warning):
during a disaster, availability matters more than strict throttling.
"""

from __future__ import annotations

import logging
import time

log = logging.getLogger("gateway.ratelimit")


class RateLimiter:
    def __init__(self, redis_url: str | None, enabled: bool = True):
        self.redis = None
        if enabled and redis_url:
            import redis.asyncio as redis

            self.redis = redis.from_url(redis_url, socket_timeout=0.2, socket_connect_timeout=0.2)
        elif enabled:
            log.warning("rate limiting disabled: no REDIS_URL / REDIS_HOST configured")

    async def hit(self, key: str, limit: int, window_seconds: int = 60) -> tuple[bool, int]:
        """Count one request for ``key``. Returns (allowed, seconds until the window resets)."""
        if self.redis is None or limit <= 0:
            return True, 0
        window = int(time.time() // window_seconds)
        retry_after = window_seconds - int(time.time() % window_seconds)
        redis_key = f"rl:{key}:{window}"
        try:
            async with self.redis.pipeline(transaction=True) as pipe:
                count, _ = await pipe.incr(redis_key).expire(redis_key, window_seconds + 5).execute()
        except Exception:
            log.warning("redis unavailable, allowing request", exc_info=True)
            return True, 0
        return count <= limit, retry_after

    async def ping(self) -> bool:
        if self.redis is None:
            return True
        try:
            return bool(await self.redis.ping())
        except Exception:
            return False

    async def close(self) -> None:
        if self.redis is not None:
            await self.redis.aclose()

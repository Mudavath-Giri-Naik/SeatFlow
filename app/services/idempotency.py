"""Idempotency-Key support backed by Redis.

Semantics:
  - First request with a given key claims it (SET NX) and proceeds.
  - A concurrent duplicate (same key, still processing) gets told to wait/retry.
  - A later duplicate (after the first finished) gets the stored response
    replayed verbatim instead of re-running the booking/payment logic.
"""

import json
import uuid
from typing import Any

from redis.asyncio import Redis

DEFAULT_TTL_SECONDS = 24 * 60 * 60
_IN_PROGRESS_SENTINEL = "__IN_PROGRESS__"


class IdempotencyInProgress(Exception):
    """Raised when a duplicate request arrives while the original is still processing."""


def _key(user_id: uuid.UUID | str, idempotency_key: str) -> str:
    return f"idempotency:{user_id}:{idempotency_key}"


async def claim_or_get_cached(
    redis: Redis,
    user_id: uuid.UUID | str,
    idempotency_key: str,
    ttl: int = DEFAULT_TTL_SECONDS,
) -> tuple[int, dict[str, Any]] | None:
    """Try to claim this idempotency key for processing.

    Returns None if the caller has claimed the key and should proceed.
    Returns (status_code, body) if a completed result is already cached.
    Raises IdempotencyInProgress if another request holds the key right now.
    """
    key = _key(user_id, idempotency_key)
    claimed = await redis.set(key, _IN_PROGRESS_SENTINEL, nx=True, ex=ttl)
    if claimed:
        return None

    raw = await redis.get(key)
    if raw is None:
        # Lost a race with a concurrent finisher clearing/expiring; caller can retry.
        raise IdempotencyInProgress()
    if raw == _IN_PROGRESS_SENTINEL:
        raise IdempotencyInProgress()

    data = json.loads(raw)
    return data["status_code"], data["body"]


async def store_result(
    redis: Redis,
    user_id: uuid.UUID | str,
    idempotency_key: str,
    status_code: int,
    body: dict[str, Any],
    ttl: int = DEFAULT_TTL_SECONDS,
) -> None:
    key = _key(user_id, idempotency_key)
    await redis.set(key, json.dumps({"status_code": status_code, "body": body}), ex=ttl)


async def release_claim(redis: Redis, user_id: uuid.UUID | str, idempotency_key: str) -> None:
    """Clear an in-progress claim on failure, so the client can safely retry
    with the same key instead of being stuck for the full TTL."""
    await redis.delete(_key(user_id, idempotency_key))

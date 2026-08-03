"""Real-time seat updates via Redis Pub/Sub.

We publish through Redis (rather than an in-process connection registry) so
that broadcasts work correctly across multiple API worker processes
(gunicorn/uvicorn workers in production, Phase 3) — a hold made against
worker A must reach a client whose WebSocket happens to be connected to
worker B.
"""

import asyncio
import json
import uuid
from typing import Any

from redis.asyncio import Redis
from starlette.websockets import WebSocket, WebSocketDisconnect

from app.core.logging_config import logger


def _channel(show_id: uuid.UUID | str) -> str:
    return f"show:{show_id}:events"


async def publish_seat_event(redis: Redis, show_id: uuid.UUID | str, event: dict[str, Any]) -> None:
    await redis.publish(_channel(show_id), json.dumps(event))


async def _forward_pubsub_to_client(pubsub, websocket: WebSocket) -> None:
    async for message in pubsub.listen():
        if message.get("type") != "message":
            continue
        await websocket.send_text(message["data"])


async def _watch_for_disconnect(websocket: WebSocket) -> None:
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        return


async def stream_show_events(websocket: WebSocket, redis: Redis, show_id: uuid.UUID | str) -> None:
    await websocket.accept()
    logger.debug("websocket connected: show={}", show_id)
    pubsub = redis.pubsub()
    channel = _channel(show_id)
    await pubsub.subscribe(channel)

    forward_task = asyncio.create_task(_forward_pubsub_to_client(pubsub, websocket))
    disconnect_task = asyncio.create_task(_watch_for_disconnect(websocket))

    try:
        done, pending = await asyncio.wait(
            {forward_task, disconnect_task}, return_when=asyncio.FIRST_COMPLETED
        )
        for task in pending:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        for task in done:
            exc = task.exception()
            if exc is not None and not isinstance(exc, WebSocketDisconnect):
                raise exc
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.aclose()
        logger.debug("websocket disconnected: show={}", show_id)

import uuid

from fastapi import APIRouter, WebSocket

from app.core.redis import get_redis_client
from app.core.ws import stream_show_events

router = APIRouter()


@router.websocket("/ws/shows/{show_id}")
async def show_events_websocket(websocket: WebSocket, show_id: uuid.UUID) -> None:
    redis = get_redis_client()
    await stream_show_events(websocket, redis, show_id)

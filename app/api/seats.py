import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.core.rate_limit import limiter
from app.core.redis import get_redis
from app.core.ws import publish_seat_event
from app.models.seat import Seat
from app.models.user import User
from app.schemas.booking import BookingRead
from app.schemas.seat import SeatRead
from app.services import booking_service
from app.services.exceptions import (
    SeatAlreadyBookedError,
    SeatAlreadyHeldError,
    SeatNotFoundError,
)

router = APIRouter(tags=["seats"])


@router.get("/shows/{show_id}/seats", response_model=list[SeatRead])
async def get_show_seats(
    show_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> list[Seat]:
    result = await db.execute(
        select(Seat).where(Seat.show_id == show_id).order_by(Seat.row_label, Seat.seat_number)
    )
    seats = list(result.scalars().all())
    return [await booking_service.reconcile_seat_status(db, redis, seat) for seat in seats]


@router.post("/seats/{seat_id}/hold", response_model=BookingRead)
@limiter.limit("10/minute")
async def hold_seat_endpoint(
    request: Request,
    seat_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    try:
        booking = await booking_service.hold_seat(
            db, redis, seat_id, current_user.id, ttl_seconds=settings.SEAT_HOLD_TTL_SECONDS
        )
    except SeatNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except SeatAlreadyBookedError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except SeatAlreadyHeldError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    seat = await db.get(Seat, seat_id)
    await publish_seat_event(
        redis, seat.show_id, {"event": "held", "seat_id": str(seat_id), "status": seat.status.value}
    )
    return booking

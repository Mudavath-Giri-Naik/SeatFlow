import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.rate_limit import limiter
from app.core.redis import get_redis
from app.core.ws import publish_seat_event
from app.models.booking import Booking, BookingStatus
from app.models.seat import Seat
from app.models.user import User
from app.schemas.booking import BookingCreate, BookingRead
from app.services import booking_service, payment_service
from app.services.exceptions import (
    SeatAlreadyBookedError,
    SeatNotFoundError,
    SeatNotHeldByUserError,
)
from app.services.idempotency import IdempotencyInProgress, claim_or_get_cached, release_claim, store_result
from app.services.payment_service import PaymentError

router = APIRouter(prefix="/bookings", tags=["bookings"])


@router.post("/confirm", response_model=BookingRead)
@limiter.limit("10/minute")
async def confirm_booking_endpoint(
    request: Request,
    payload: BookingCreate,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    try:
        cached = await claim_or_get_cached(redis, current_user.id, idempotency_key)
    except IdempotencyInProgress as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A request with this Idempotency-Key is already being processed",
        ) from exc

    if cached is not None:
        status_code, body = cached
        return JSONResponse(status_code=status_code, content=body)

    try:
        seat = await db.get(Seat, payload.seat_id)
        if seat is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Seat not found")

        try:
            await payment_service.charge(current_user.id, seat.id, seat.price)
        except PaymentError as exc:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail="Payment failed after retries - seat hold preserved, please try again",
            ) from exc

        try:
            booking = await booking_service.confirm_booking(db, redis, seat.id, current_user.id)
        except SeatNotHeldByUserError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        except SeatAlreadyBookedError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        except SeatNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

        body = jsonable_encoder(BookingRead.model_validate(booking))
        await store_result(redis, current_user.id, idempotency_key, status.HTTP_200_OK, body)
        await publish_seat_event(
            redis, seat.show_id, {"event": "booked", "seat_id": str(seat.id), "status": "booked"}
        )
        return booking
    except HTTPException:
        # Business failure (payment declined, seat lost, etc): free the key so
        # the same Idempotency-Key can be retried instead of being stuck.
        await release_claim(redis, current_user.id, idempotency_key)
        raise
    except Exception:
        await release_claim(redis, current_user.id, idempotency_key)
        raise


@router.post("/{booking_id}/cancel", response_model=BookingRead)
async def cancel_booking(
    booking_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> Booking:
    booking = await db.get(Booking, booking_id)
    if booking is None or booking.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")
    if booking.status == BookingStatus.CANCELLED:
        return booking

    seat = await db.get(Seat, booking.seat_id)
    await booking_service.cancel_booking(db, redis, booking)

    if seat is not None:
        await publish_seat_event(
            redis, seat.show_id, {"event": "released", "seat_id": str(seat.id), "status": "available"}
        )
    return booking

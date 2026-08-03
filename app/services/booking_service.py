"""Core booking domain logic.

Deliberately framework-agnostic: no FastAPI imports. Callers (API routers,
tests, scripts) pass in an AsyncSession and a Redis client explicitly.

Concurrency strategy:
  - A Redis lock (SET NX PX) is the fast, cheap gate that stops two users from
    even attempting to hold the same seat at the same time. It has a TTL so an
    abandoned hold (closed tab, crashed client) self-expires.
  - SELECT ... FOR UPDATE on the seat row is the authoritative gate at confirm
    time — it guarantees that even if two requests somehow both believe they
    hold the seat, only one can actually flip it to BOOKED, because the second
    transaction blocks on the row lock until the first commits, then sees the
    already-BOOKED status and aborts.
"""

import uuid
from datetime import UTC, datetime

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging_config import logger
from app.models.booking import Booking, BookingStatus
from app.models.seat import Seat, SeatStatus
from app.services.exceptions import (
    SeatAlreadyBookedError,
    SeatAlreadyHeldError,
    SeatNotFoundError,
    SeatNotHeldByUserError,
)

DEFAULT_HOLD_TTL_SECONDS = 120

_RELEASE_LOCK_SCRIPT = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
else
    return 0
end
"""


def _lock_key(seat_id: uuid.UUID | str) -> str:
    return f"seat_lock:{seat_id}"


async def _release_lock_if_owner(redis: Redis, seat_id: uuid.UUID | str, user_id: uuid.UUID | str) -> bool:
    result = await redis.eval(_RELEASE_LOCK_SCRIPT, 1, _lock_key(seat_id), str(user_id))
    return bool(result)


async def get_lock_owner(redis: Redis, seat_id: uuid.UUID | str) -> str | None:
    return await redis.get(_lock_key(seat_id))


async def hold_seat(
    db: AsyncSession,
    redis: Redis,
    seat_id: uuid.UUID,
    user_id: uuid.UUID,
    ttl_seconds: int = DEFAULT_HOLD_TTL_SECONDS,
) -> Booking:
    """Attempt to acquire a short-lived hold on a seat for a user.

    Fails cleanly (raises SeatAlreadyHeldError) if another user already holds
    the seat. Re-holding by the same user simply refreshes the TTL (idempotent).
    """
    seat = await db.get(Seat, seat_id)
    if seat is None:
        raise SeatNotFoundError(f"seat {seat_id} not found")
    if seat.status == SeatStatus.BOOKED:
        raise SeatAlreadyBookedError(f"seat {seat_id} is already booked")

    lock_key = _lock_key(seat_id)
    acquired = await redis.set(lock_key, str(user_id), nx=True, ex=ttl_seconds)

    if not acquired:
        owner = await redis.get(lock_key)
        if owner != str(user_id):
            logger.info("hold rejected: seat={} already held by another user", seat_id)
            raise SeatAlreadyHeldError(f"seat {seat_id} is currently held by another user")
        # Same user re-holding: refresh TTL, proceed.
        await redis.expire(lock_key, ttl_seconds)

    seat.status = SeatStatus.HELD

    result = await db.execute(
        select(Booking).where(Booking.seat_id == seat_id, Booking.status == BookingStatus.HELD)
    )
    booking = result.scalar_one_or_none()
    now = datetime.now(UTC)
    if booking is None:
        booking = Booking(seat_id=seat_id, user_id=user_id, status=BookingStatus.HELD, held_at=now)
        db.add(booking)
    else:
        booking.user_id = user_id
        booking.held_at = now

    await db.commit()
    await db.refresh(booking)
    logger.info("seat held: seat={} user={} ttl={}s", seat_id, user_id, ttl_seconds)
    return booking


async def confirm_booking(db: AsyncSession, redis: Redis, seat_id: uuid.UUID, user_id: uuid.UUID) -> Booking:
    """Confirm a held seat into a real booking.

    Requires the caller to currently hold the Redis lock for this seat. The
    actual state transition is guarded by SELECT ... FOR UPDATE so it is safe
    even if this check-then-act sequence races with another confirm.
    """
    owner = await redis.get(_lock_key(seat_id))
    if owner is None or owner != str(user_id):
        logger.warning("confirm rejected: seat={} user={} does not hold the lock", seat_id, user_id)
        raise SeatNotHeldByUserError(f"user {user_id} does not currently hold seat {seat_id}")

    result = await db.execute(select(Seat).where(Seat.id == seat_id).with_for_update())
    seat = result.scalar_one_or_none()
    if seat is None:
        raise SeatNotFoundError(f"seat {seat_id} not found")
    if seat.status == SeatStatus.BOOKED:
        logger.warning("confirm rejected: seat={} already booked (lost the race)", seat_id)
        raise SeatAlreadyBookedError(f"seat {seat_id} is already booked")

    booking_result = await db.execute(
        select(Booking)
        .where(Booking.seat_id == seat_id, Booking.status == BookingStatus.HELD)
        .with_for_update()
    )
    booking = booking_result.scalar_one_or_none()
    now = datetime.now(UTC)
    if booking is None:
        booking = Booking(seat_id=seat_id, user_id=user_id, status=BookingStatus.HELD, held_at=now)
        db.add(booking)

    seat.status = SeatStatus.BOOKED
    booking.status = BookingStatus.CONFIRMED
    booking.confirmed_at = now

    await db.commit()
    await db.refresh(booking)

    # Seat is permanently booked now; the hold lock has served its purpose.
    await _release_lock_if_owner(redis, seat_id, user_id)

    logger.info("booking confirmed: seat={} user={} booking={}", seat_id, user_id, booking.id)
    return booking


async def release_seat(
    db: AsyncSession,
    redis: Redis,
    seat_id: uuid.UUID,
    user_id: uuid.UUID | None = None,
) -> None:
    """Release a seat's hold (timeout or explicit cancellation).

    If user_id is given, only releases the Redis lock when it's actually
    owned by that user (atomic compare-and-delete). If user_id is None, the
    lock is force-deleted (used by background reconciliation / admin paths).
    """
    if user_id is not None:
        await _release_lock_if_owner(redis, seat_id, user_id)
    else:
        await redis.delete(_lock_key(seat_id))

    seat = await db.get(Seat, seat_id)
    if seat is None or seat.status != SeatStatus.HELD:
        return

    seat.status = SeatStatus.AVAILABLE

    result = await db.execute(
        select(Booking).where(Booking.seat_id == seat_id, Booking.status == BookingStatus.HELD)
    )
    booking = result.scalar_one_or_none()
    if booking is not None:
        booking.status = BookingStatus.CANCELLED
        booking.cancelled_at = datetime.now(UTC)

    await db.commit()


async def cancel_booking(db: AsyncSession, redis: Redis, booking: Booking) -> Booking:
    """Cancel a booking regardless of whether it was only held or already
    confirmed, freeing the seat back to AVAILABLE. Confirmed cancellations
    are guarded by SELECT ... FOR UPDATE for the same reason confirm_booking
    is: this flips a booked seat's status and must not race a concurrent
    confirm attempt on a lock that's expiring at the same moment."""
    if booking.status == BookingStatus.CANCELLED:
        return booking

    if booking.status == BookingStatus.HELD:
        await release_seat(db, redis, booking.seat_id, booking.user_id)
        await db.refresh(booking)
        return booking

    result = await db.execute(select(Seat).where(Seat.id == booking.seat_id).with_for_update())
    seat = result.scalar_one_or_none()
    if seat is not None:
        seat.status = SeatStatus.AVAILABLE

    booking.status = BookingStatus.CANCELLED
    booking.cancelled_at = datetime.now(UTC)

    await db.commit()
    await db.refresh(booking)
    await redis.delete(_lock_key(booking.seat_id))
    return booking


async def reconcile_seat_status(db: AsyncSession, redis: Redis, seat: Seat) -> Seat:
    """Self-healing read: if a seat is marked HELD but its Redis lock has
    expired (client vanished without releasing), flip it back to AVAILABLE.
    Called on read paths (e.g. GET /shows/{id}/seats) so stale holds don't
    linger in Postgres past their TTL."""
    if seat.status == SeatStatus.HELD:
        owner = await redis.get(_lock_key(seat.id))
        if owner is None:
            await release_seat(db, redis, seat.id, user_id=None)
            await db.refresh(seat)
    return seat

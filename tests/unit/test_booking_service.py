"""Unit tests for app.services.booking_service with Redis/DB fully mocked.

These test the branching logic in isolation (lock contention, missing seat,
already-booked seat, etc.) without needing any real infrastructure.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.booking import Booking, BookingStatus
from app.models.seat import Seat, SeatStatus
from app.services import booking_service
from app.services.exceptions import (
    SeatAlreadyBookedError,
    SeatAlreadyHeldError,
    SeatNotFoundError,
    SeatNotHeldByUserError,
)


def make_seat(status: SeatStatus = SeatStatus.AVAILABLE) -> Seat:
    return Seat(id=uuid.uuid4(), show_id=uuid.uuid4(), row_label="A", seat_number=1, price=10, status=status)


def make_db(execute_result=None) -> AsyncMock:
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = execute_result
    db.execute = AsyncMock(return_value=result)
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.add = MagicMock()  # AsyncSession.add() is synchronous, unlike most Session methods
    return db


async def test_hold_seat_success_creates_held_booking():
    seat = make_seat()
    db = make_db(execute_result=None)
    db.get = AsyncMock(return_value=seat)

    redis = AsyncMock()
    redis.set = AsyncMock(return_value=True)

    user_id = uuid.uuid4()
    booking = await booking_service.hold_seat(db, redis, seat.id, user_id, ttl_seconds=60)

    assert seat.status == SeatStatus.HELD
    assert booking.status == BookingStatus.HELD
    assert booking.user_id == user_id
    redis.set.assert_awaited_once()
    db.commit.assert_awaited_once()


async def test_hold_seat_fails_when_locked_by_another_user():
    seat = make_seat()
    db = make_db()
    db.get = AsyncMock(return_value=seat)

    redis = AsyncMock()
    redis.set = AsyncMock(return_value=None)  # NX failed
    redis.get = AsyncMock(return_value=str(uuid.uuid4()))  # locked by someone else

    with pytest.raises(SeatAlreadyHeldError):
        await booking_service.hold_seat(db, redis, seat.id, uuid.uuid4())


async def test_hold_seat_same_user_refreshes_ttl_instead_of_failing():
    user_id = uuid.uuid4()
    seat = make_seat()
    db = make_db(execute_result=None)
    db.get = AsyncMock(return_value=seat)

    redis = AsyncMock()
    redis.set = AsyncMock(return_value=None)
    redis.get = AsyncMock(return_value=str(user_id))  # already held by same user
    redis.expire = AsyncMock()

    booking = await booking_service.hold_seat(db, redis, seat.id, user_id, ttl_seconds=60)

    redis.expire.assert_awaited_once()
    assert booking.status == BookingStatus.HELD


async def test_hold_seat_raises_when_seat_missing():
    db = make_db()
    db.get = AsyncMock(return_value=None)
    redis = AsyncMock()

    with pytest.raises(SeatNotFoundError):
        await booking_service.hold_seat(db, redis, uuid.uuid4(), uuid.uuid4())


async def test_hold_seat_raises_when_already_booked():
    seat = make_seat(status=SeatStatus.BOOKED)
    db = make_db()
    db.get = AsyncMock(return_value=seat)
    redis = AsyncMock()

    with pytest.raises(SeatAlreadyBookedError):
        await booking_service.hold_seat(db, redis, seat.id, uuid.uuid4())


async def test_confirm_booking_requires_holding_the_lock():
    seat = make_seat(status=SeatStatus.HELD)
    db = make_db()
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)

    with pytest.raises(SeatNotHeldByUserError):
        await booking_service.confirm_booking(db, redis, seat.id, uuid.uuid4())


async def test_confirm_booking_rejects_wrong_owner():
    seat = make_seat(status=SeatStatus.HELD)
    db = make_db()
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=str(uuid.uuid4()))  # different owner

    with pytest.raises(SeatNotHeldByUserError):
        await booking_service.confirm_booking(db, redis, seat.id, uuid.uuid4())


async def test_confirm_booking_success_books_seat_and_releases_lock():
    user_id = uuid.uuid4()
    seat = make_seat(status=SeatStatus.HELD)
    existing_booking = Booking(id=uuid.uuid4(), seat_id=seat.id, user_id=user_id, status=BookingStatus.HELD)

    db = AsyncMock()
    seat_result = MagicMock()
    seat_result.scalar_one_or_none.return_value = seat
    booking_result = MagicMock()
    booking_result.scalar_one_or_none.return_value = existing_booking
    db.execute = AsyncMock(side_effect=[seat_result, booking_result])
    db.commit = AsyncMock()
    db.refresh = AsyncMock()

    redis = AsyncMock()
    redis.get = AsyncMock(return_value=str(user_id))
    redis.eval = AsyncMock(return_value=1)

    booking = await booking_service.confirm_booking(db, redis, seat.id, user_id)

    assert seat.status == SeatStatus.BOOKED
    assert booking.status == BookingStatus.CONFIRMED
    assert booking.confirmed_at is not None
    redis.eval.assert_awaited_once()


async def test_confirm_booking_raises_when_seat_already_booked():
    user_id = uuid.uuid4()
    seat = make_seat(status=SeatStatus.BOOKED)
    db = make_db(execute_result=seat)
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=str(user_id))

    with pytest.raises(SeatAlreadyBookedError):
        await booking_service.confirm_booking(db, redis, seat.id, user_id)

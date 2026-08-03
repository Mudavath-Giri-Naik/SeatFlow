"""Integration tests running the full hold -> confirm flow against a real
Postgres + Redis (see tests/conftest.py for how those are provided /
skipped)."""

import uuid

import pytest

from app.models.booking import BookingStatus
from app.models.seat import SeatStatus
from app.services import booking_service
from app.services.exceptions import SeatAlreadyHeldError, SeatNotHeldByUserError


async def test_hold_then_confirm_flow(db_session, redis_client, seeded_seat):
    user_id = uuid.uuid4()

    held = await booking_service.hold_seat(db_session, redis_client, seeded_seat.id, user_id, ttl_seconds=60)
    assert held.status == BookingStatus.HELD

    await db_session.refresh(seeded_seat)
    assert seeded_seat.status == SeatStatus.HELD

    confirmed = await booking_service.confirm_booking(db_session, redis_client, seeded_seat.id, user_id)
    assert confirmed.status == BookingStatus.CONFIRMED
    assert confirmed.id == held.id

    await db_session.refresh(seeded_seat)
    assert seeded_seat.status == SeatStatus.BOOKED

    # Lock should be released after a successful confirm.
    assert await redis_client.get(f"seat_lock:{seeded_seat.id}") is None


async def test_second_user_cannot_hold_seat_already_held(db_session, redis_client, seeded_seat):
    user_a, user_b = uuid.uuid4(), uuid.uuid4()

    await booking_service.hold_seat(db_session, redis_client, seeded_seat.id, user_a, ttl_seconds=60)

    with pytest.raises(SeatAlreadyHeldError):
        await booking_service.hold_seat(db_session, redis_client, seeded_seat.id, user_b, ttl_seconds=60)


async def test_second_user_cannot_confirm_seat_held_by_someone_else(db_session, redis_client, seeded_seat):
    user_a, user_b = uuid.uuid4(), uuid.uuid4()

    await booking_service.hold_seat(db_session, redis_client, seeded_seat.id, user_a, ttl_seconds=60)

    with pytest.raises(SeatNotHeldByUserError):
        await booking_service.confirm_booking(db_session, redis_client, seeded_seat.id, user_b)


async def test_release_then_hold_by_different_user(db_session, redis_client, seeded_seat):
    user_a, user_b = uuid.uuid4(), uuid.uuid4()

    await booking_service.hold_seat(db_session, redis_client, seeded_seat.id, user_a, ttl_seconds=60)
    await booking_service.release_seat(db_session, redis_client, seeded_seat.id, user_a)

    await db_session.refresh(seeded_seat)
    assert seeded_seat.status == SeatStatus.AVAILABLE

    held = await booking_service.hold_seat(db_session, redis_client, seeded_seat.id, user_b, ttl_seconds=60)
    assert held.user_id == user_b

"""The concurrency test: fires two simultaneous hold attempts at the same
seat and asserts exactly one succeeds. Each attempt uses its own DB session
(mirroring two independent API requests) so the only thing preventing a
double-hold is the Redis lock in booking_service.hold_seat."""

import asyncio
import uuid

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.services import booking_service
from app.services.exceptions import SeatAlreadyHeldError


async def test_exactly_one_of_two_simultaneous_holds_succeeds(db_engine, redis_client, seeded_seat):
    session_maker = async_sessionmaker(bind=db_engine, expire_on_commit=False)
    user_a, user_b = uuid.uuid4(), uuid.uuid4()

    async def attempt(user_id: uuid.UUID) -> bool:
        async with session_maker() as session:
            try:
                await booking_service.hold_seat(session, redis_client, seeded_seat.id, user_id, ttl_seconds=30)
                return True
            except SeatAlreadyHeldError:
                return False

    results = await asyncio.gather(attempt(user_a), attempt(user_b))

    assert results.count(True) == 1
    assert results.count(False) == 1


async def test_many_simultaneous_holds_on_one_seat_only_one_wins(db_engine, redis_client, seeded_seat):
    session_maker = async_sessionmaker(bind=db_engine, expire_on_commit=False)
    user_ids = [uuid.uuid4() for _ in range(20)]

    async def attempt(user_id: uuid.UUID) -> bool:
        async with session_maker() as session:
            try:
                await booking_service.hold_seat(session, redis_client, seeded_seat.id, user_id, ttl_seconds=30)
                return True
            except SeatAlreadyHeldError:
                return False

    results = await asyncio.gather(*(attempt(uid) for uid in user_ids))

    assert results.count(True) == 1

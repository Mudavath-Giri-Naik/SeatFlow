"""Shared pytest fixtures.

Unit tests (tests/unit/) mock Redis/DB entirely and never touch this file's
infra fixtures. Integration tests (tests/integration/) use `db_session` /
`redis_client` below, which talk to the real Postgres + Redis configured via
DATABASE_URL / REDIS_URL (e.g. the ones docker-compose brings up). If those
aren't reachable, integration tests skip with a clear message instead of
erroring — so `pytest` still passes in an environment with no Docker.

Note: integration tests create/drop tables and flush Redis against whatever
DATABASE_URL/REDIS_URL point at. Point those at a disposable instance (the
docker-compose ones are fine) — don't run against a database you care about.
"""

from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from redis.asyncio import Redis, from_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.models import Base
from app.models.seat import Seat
from app.models.show import Show
from app.models.venue import Venue


async def _postgres_reachable() -> bool:
    try:
        engine = create_async_engine(settings.DATABASE_URL)
        async with engine.connect():
            pass
        await engine.dispose()
        return True
    except Exception:
        return False


async def _redis_reachable() -> bool:
    try:
        client = from_url(settings.REDIS_URL, decode_responses=True)
        await client.ping()
        await client.aclose()
        return True
    except Exception:
        return False


@pytest_asyncio.fixture
async def require_infra() -> None:
    if not await _postgres_reachable() or not await _redis_reachable():
        pytest.skip(
            "Postgres and/or Redis are not reachable at the configured DATABASE_URL/"
            "REDIS_URL — run `docker-compose up -d` first to run integration tests."
        )


@pytest_asyncio.fixture
async def db_engine(require_infra: None):
    engine = create_async_engine(settings.DATABASE_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine) -> AsyncGenerator[AsyncSession, None]:
    session_maker = async_sessionmaker(bind=db_engine, expire_on_commit=False)
    async with session_maker() as session:
        yield session


@pytest_asyncio.fixture
async def redis_client(require_infra: None) -> AsyncGenerator[Redis, None]:
    client = from_url(settings.REDIS_URL, decode_responses=True)
    await client.flushdb()
    yield client
    await client.flushdb()
    await client.aclose()


@pytest_asyncio.fixture
async def seeded_seat(db_session: AsyncSession) -> Seat:
    venue = Venue(name="Test Venue")
    db_session.add(venue)
    await db_session.flush()

    show = Show(venue_id=venue.id, title="Test Show", starts_at=datetime.now(UTC) + timedelta(days=1))
    db_session.add(show)
    await db_session.flush()

    seat = Seat(show_id=show.id, row_label="A", seat_number=1, price=25)
    db_session.add(seat)
    await db_session.commit()
    await db_session.refresh(seat)
    return seat

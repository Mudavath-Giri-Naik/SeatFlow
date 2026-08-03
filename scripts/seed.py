"""Seed the database with a demo venue, show, and a small grid of seats.

Usage (from the project root, with postgres+redis running and migrations applied):
    python -m scripts.seed
"""

import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.seat import Seat
from app.models.show import Show
from app.models.venue import Venue

ROWS = ["A", "B", "C"]
SEATS_PER_ROW = 5


async def seed() -> None:
    async with AsyncSessionLocal() as db:
        existing = await db.execute(select(Venue).where(Venue.name == "Demo Arena"))
        venue = existing.scalar_one_or_none()
        if venue is None:
            venue = Venue(name="Demo Arena", address="1 Main St", city="Metropolis")
            db.add(venue)
            await db.flush()

        existing_show = await db.execute(select(Show).where(Show.venue_id == venue.id))
        show = existing_show.scalar_one_or_none()
        if show is None:
            show = Show(
                venue_id=venue.id,
                title="Opening Night",
                starts_at=datetime.now(UTC) + timedelta(days=7),
            )
            db.add(show)
            await db.flush()

        existing_seats = await db.execute(select(Seat).where(Seat.show_id == show.id))
        if not existing_seats.scalars().first():
            for row in ROWS:
                for number in range(1, SEATS_PER_ROW + 1):
                    db.add(Seat(show_id=show.id, row_label=row, seat_number=number, price=49.99))

        await db.commit()
        print(f"Venue:  {venue.id}  ({venue.name})")
        print(f"Show:   {show.id}  ({show.title})")
        print(f"Seats:  {len(ROWS) * SEATS_PER_ROW} seeded (or already present)")


if __name__ == "__main__":
    asyncio.run(seed())

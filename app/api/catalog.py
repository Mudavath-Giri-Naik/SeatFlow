"""Minimal admin/catalog endpoints for creating venues, shows, and seats.

Not the focus of this project (seat booking concurrency is), but needed so a
venue/show/seat can be created through /docs instead of only via the seed
script.
"""

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.seat import Seat
from app.models.show import Show
from app.models.user import User
from app.models.venue import Venue
from app.schemas.seat import SeatCreate, SeatRead
from app.schemas.show import ShowCreate, ShowRead
from app.schemas.venue import VenueCreate, VenueRead

router = APIRouter(tags=["catalog"])


@router.post("/venues", response_model=VenueRead, status_code=status.HTTP_201_CREATED)
async def create_venue(
    payload: VenueCreate,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> Venue:
    venue = Venue(**payload.model_dump())
    db.add(venue)
    await db.commit()
    await db.refresh(venue)
    return venue


@router.get("/venues", response_model=list[VenueRead])
async def list_venues(db: AsyncSession = Depends(get_db)) -> list[Venue]:
    result = await db.execute(select(Venue))
    return list(result.scalars().all())


@router.post("/shows", response_model=ShowRead, status_code=status.HTTP_201_CREATED)
async def create_show(
    payload: ShowCreate,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> Show:
    show = Show(**payload.model_dump())
    db.add(show)
    await db.commit()
    await db.refresh(show)
    return show


@router.get("/shows", response_model=list[ShowRead])
async def list_shows(db: AsyncSession = Depends(get_db)) -> list[Show]:
    result = await db.execute(select(Show))
    return list(result.scalars().all())


@router.post("/seats", response_model=SeatRead, status_code=status.HTTP_201_CREATED)
async def create_seat(
    payload: SeatCreate,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> Seat:
    seat = Seat(**payload.model_dump())
    db.add(seat)
    await db.commit()
    await db.refresh(seat)
    return seat

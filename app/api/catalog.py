"""Minimal admin/catalog endpoints for creating venues, shows, and seats.

Not the focus of this project (seat booking concurrency is), but needed so a
venue/show/seat can be created through /docs instead of only via the seed
script.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

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
    result = await db.execute(select(Show).options(selectinload(Show.venue)).where(Show.id == show.id))
    return result.scalar_one()


@router.get("/shows", response_model=list[ShowRead])
async def list_shows(db: AsyncSession = Depends(get_db)) -> list[Show]:
    result = await db.execute(select(Show).options(selectinload(Show.venue)).order_by(Show.starts_at))
    return list(result.scalars().all())


@router.get("/shows/{show_id}", response_model=ShowRead)
async def get_show(show_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> Show:
    result = await db.execute(select(Show).options(selectinload(Show.venue)).where(Show.id == show_id))
    show = result.scalar_one_or_none()
    if show is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Show not found")
    return show


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

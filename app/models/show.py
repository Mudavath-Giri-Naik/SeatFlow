import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPKMixin


class Show(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "shows"

    venue_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("venues.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    venue: Mapped["Venue"] = relationship(back_populates="shows")  # noqa: F821
    seats: Mapped[list["Seat"]] = relationship(back_populates="show", cascade="all, delete-orphan")  # noqa: F821

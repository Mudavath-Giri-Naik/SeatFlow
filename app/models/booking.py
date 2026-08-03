import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPKMixin


class BookingStatus(str, enum.Enum):
    HELD = "held"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


class Booking(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "bookings"

    seat_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("seats.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[BookingStatus] = mapped_column(
        Enum(BookingStatus, name="booking_status"), default=BookingStatus.HELD, nullable=False
    )

    held_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    seat: Mapped["Seat"] = relationship(back_populates="bookings")  # noqa: F821
    user: Mapped["User"] = relationship(back_populates="bookings")  # noqa: F821

import enum
import uuid

from sqlalchemy import Enum, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPKMixin


class SeatStatus(str, enum.Enum):
    AVAILABLE = "available"
    HELD = "held"
    BOOKED = "booked"


class Seat(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "seats"
    __table_args__ = (UniqueConstraint("show_id", "row_label", "seat_number", name="uq_seat_position_per_show"),)

    show_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("shows.id", ondelete="CASCADE"), nullable=False)
    row_label: Mapped[str] = mapped_column(String(10), nullable=False)
    seat_number: Mapped[int] = mapped_column(Integer, nullable=False)
    price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    status: Mapped[SeatStatus] = mapped_column(
        Enum(SeatStatus, name="seat_status", values_callable=lambda enum_cls: [e.value for e in enum_cls]),
        default=SeatStatus.AVAILABLE,
        nullable=False,
    )

    show: Mapped["Show"] = relationship(back_populates="seats")  # noqa: F821
    bookings: Mapped[list["Booking"]] = relationship(back_populates="seat")  # noqa: F821

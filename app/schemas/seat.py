import uuid
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.models.seat import SeatStatus


class SeatCreate(BaseModel):
    show_id: uuid.UUID
    row_label: str
    seat_number: int
    price: Decimal = Decimal("0")


class SeatRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    show_id: uuid.UUID
    row_label: str
    seat_number: int
    price: Decimal
    status: SeatStatus

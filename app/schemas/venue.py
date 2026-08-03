import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class VenueCreate(BaseModel):
    name: str
    address: str | None = None
    city: str | None = None


class VenueRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    address: str | None
    city: str | None
    created_at: datetime

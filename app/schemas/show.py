import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ShowCreate(BaseModel):
    venue_id: uuid.UUID
    title: str
    starts_at: datetime


class ShowRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    venue_id: uuid.UUID
    title: str
    starts_at: datetime
    created_at: datetime

from datetime import datetime
from pydantic import BaseModel, Field


class EventCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    kind: str
    summary: str | None = Field(default=None, max_length=1000)


class EventOut(EventCreate):
    id: str
    status: str
    created_at: datetime
    version: int


class TeamCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class TeamOut(TeamCreate):
    id: str
    event_id: str
    status: str
    version: int


class PositionCreate(BaseModel):
    id: str
    event_id: str
    device_id: str
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    alt_m: float | None = None
    accuracy_m: float | None = Field(default=None, ge=0)
    heading_deg: float | None = Field(default=None, ge=0, lt=360)
    speed_mps: float | None = Field(default=None, ge=0)
    time: datetime


class PositionOut(PositionCreate):
    pass


class POICreate(BaseModel):
    id: str
    kind: str = Field(min_length=1, max_length=64)
    label: str | None = Field(default=None, max_length=160)
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class POIOut(POICreate):
    event_id: str
    created_at: datetime
    version: int

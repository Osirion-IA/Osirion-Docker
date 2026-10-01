# app/schemas/event_schemas.py
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class EventCreate(BaseModel):
    camera_id: int
    event_type: str
    confidence: Optional[float] = None
    snapshot_url: Optional[str] = None
    meta: Optional[dict] = None

class EventRead(BaseModel):
    id: int
    camera_id: int
    event_type: str
    confidence: Optional[float]
    snapshot_url: Optional[str]
    meta: Optional[dict] = None
    timestamp: datetime

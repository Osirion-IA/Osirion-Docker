# app/schemas/event_schemas.py
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class EventCreate(BaseModel):
    camera_id: int
    person_id: Optional[int] = None
    event_type: str
    confidence: Optional[float] = None
    snapshot_url: Optional[str] = None
    plate_text_detected: Optional[str] = None
    vehicle_id: Optional[int] = None

class EventRead(BaseModel):
    id: int
    camera_id: int
    person_id: Optional[int]
    event_type: str
    confidence: Optional[float]
    snapshot_url: Optional[str]
    plate_text_detected: Optional[str] = None
    vehicle_id: Optional[int] = None
    timestamp: datetime

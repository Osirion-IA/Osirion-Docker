# app/models/event.py
from sqlmodel import SQLModel, Field, Relationship
from typing import Optional
from datetime import datetime

class Event(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    camera_id: int = Field(foreign_key="camera.id")
    person_id: Optional[int] = Field(default=None, foreign_key="people.id")
    event_type: str = Field(..., max_length=30)
    confidence: Optional[float] = None
    snapshot_url: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)

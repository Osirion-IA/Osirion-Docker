# app/models/camera.py
from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import datetime
from typing import Optional
class Camera(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    cam_name: str = Field(..., max_length=50)
    rtsp_url: str
    location: Optional[str] = Field(default=None, max_length=100)
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)

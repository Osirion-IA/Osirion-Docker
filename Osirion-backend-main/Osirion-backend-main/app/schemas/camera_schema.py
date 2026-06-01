# app/schemas/camera_schemas.py
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class CameraCreate(BaseModel):
    cam_name: str
    rtsp_url: str
    location: Optional[str] = None
    is_active: Optional[bool] = True

class CameraRead(BaseModel):
    id: int
    cam_name: str
    rtsp_url: str
    location: Optional[str]
    is_active: bool
    created_at: datetime

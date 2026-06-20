# app/schemas/camera_schemas.py
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class CameraCreate(BaseModel):
    cam_name: str
    rtsp_url: str
    location: Optional[str] = None
    is_active: Optional[bool] = True

# Activation/désactivation d'une caméra sans réenvoyer tout l'objet (notamment
# pas la rtsp_url, qui serait re-chiffrée). Utilisé par PATCH /cameras/{id}/active.
class CameraActiveUpdate(BaseModel):
    is_active: bool

class CameraRead(BaseModel):
    id: int
    cam_name: str
    rtsp_url: str
    location: Optional[str]
    is_active: bool
    created_at: datetime

# app/schemas/group_schema.py
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class CameraGroupCreate(BaseModel):
    name: str
    description: Optional[str] = None


class CameraGroupUpdate(BaseModel):
    """Mise à jour PARTIELLE d'un groupe (tous les champs optionnels)."""
    name: Optional[str] = None
    description: Optional[str] = None


class CameraGroupRead(BaseModel):
    id: int
    name: str
    description: Optional[str]
    created_at: datetime
    # Caméras membres (ids) + total, pour l'affichage sans requête supplémentaire.
    camera_ids: List[int] = []
    camera_count: int = 0

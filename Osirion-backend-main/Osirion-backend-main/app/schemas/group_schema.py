# app/schemas/group_schema.py
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class CameraGroupCreate(BaseModel):
    name: str
    description: Optional[str] = None
    is_facial_active: Optional[bool] = True
    is_lpr_active: Optional[bool] = True


class CameraGroupUpdate(BaseModel):
    """Mise à jour PARTIELLE d'un groupe (tous les champs optionnels)."""
    name: Optional[str] = None
    description: Optional[str] = None
    is_facial_active: Optional[bool] = None
    is_lpr_active: Optional[bool] = None


class GroupModulesUpdate(BaseModel):
    """Basculement en masse des modules d'un groupe.

    Payload de PATCH /groups/{id}/modules, ex. {"is_facial_active": true,
    "is_lpr_active": false}. Les deux champs sont optionnels : on ne met à jour
    que ceux fournis (les autres restent inchangés).
    """
    is_facial_active: Optional[bool] = None
    is_lpr_active: Optional[bool] = None


class CameraGroupRead(BaseModel):
    id: int
    name: str
    description: Optional[str]
    is_facial_active: bool
    is_lpr_active: bool
    created_at: datetime
    # Caméras membres (ids) + total, pour l'affichage sans requête supplémentaire.
    camera_ids: List[int] = []
    camera_count: int = 0

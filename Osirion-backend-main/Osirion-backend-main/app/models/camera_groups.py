# app/models/camera_groups.py
"""
Groupes de caméras (VMS) : regroupent des caméras pour une organisation logique
du parc (et, à terme, l'application de règles/zones en masse).

Import UNIDIRECTIONNEL : ce module importe `Camera` et `CameraGroupLink` depuis
`cameras.py`. La relation inverse `Camera.groups` est déclarée côté `cameras.py`
avec une annotation en chaîne, ce qui évite tout cycle d'import à l'exécution.
"""
from sqlmodel import SQLModel, Field, Relationship
from typing import Optional, List
from datetime import datetime

from app.models.cameras import Camera, CameraGroupLink


class CameraGroup(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    # Nom unique et indexé : identifie le groupe côté UI et interdit les doublons.
    name: str = Field(..., max_length=100, unique=True, index=True)
    description: Optional[str] = Field(default=None, max_length=255)

    # indexCode de l'Area HikCentral quand le groupe provient de la synchro
    # (mapping area ↔ groupe). Vide = groupe créé manuellement.
    hik_region_code: Optional[str] = Field(default=None, index=True, max_length=64)

    created_at: datetime = Field(default_factory=datetime.utcnow)

    cameras: List[Camera] = Relationship(
        back_populates="groups",
        link_model=CameraGroupLink,
    )

# app/models/camera_groups.py
"""
Groupes de caméras (VMS) : regroupent des caméras pour un basculement de module
en masse (facial / LPR) et une organisation logique du parc.

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

    # ── Drapeaux de module au niveau du GROUPE ────────────────────────────────
    # Désactiver l'un de ces drapeaux coupe le module correspondant pour TOUTES
    # les caméras du groupe (config effective = ET logique local ∧ groupes). Le
    # Core applique le changement à chaud (aucun redémarrage de conteneur/thread).
    is_facial_active: bool = Field(default=True)
    is_lpr_active: bool = Field(default=True)

    created_at: datetime = Field(default_factory=datetime.utcnow)

    cameras: List[Camera] = Relationship(
        back_populates="groups",
        link_model=CameraGroupLink,
    )

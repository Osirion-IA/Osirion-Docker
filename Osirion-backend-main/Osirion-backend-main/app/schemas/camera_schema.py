# app/schemas/camera_schemas.py
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class CameraCreate(BaseModel):
    cam_name: str
    rtsp_url: str
    location: Optional[str] = None
    is_active: Optional[bool] = True
    # Drapeaux de module locaux (par caméra) — défaut True (aucune régression).
    is_facial_active: Optional[bool] = True
    is_lpr_active: Optional[bool] = True
    # Métadonnées géospatiales (cartographie). Toutes optionnelles.
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    bearing: Optional[float] = Field(default=0.0, ge=0.0, le=360.0)


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

    # Drapeaux locaux + métadonnées géo.
    is_facial_active: bool = True
    is_lpr_active: bool = True
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    bearing: Optional[float] = 0.0

    # Appartenance aux groupes.
    group_ids: List[int] = []

    # ── Config EFFECTIVE des modules (calculée côté serveur) ──────────────────
    # effective = drapeau local ∧ tous les groupes de la caméra ont le module actif.
    # C'est CE que le Core lit pour activer/désactiver le pipeline à chaud.
    effective_facial_active: bool = True
    effective_lpr_active: bool = True
    # Liste plate des modules effectivement actifs (pratique pour l'UI).
    active_modules: List[str] = []

    created_at: datetime


class CameraMapData(BaseModel):
    """Payload allégé pour le composant carte OpenStreetMap / Leaflet.

    Ne contient QUE ce dont la carte a besoin (pas de rtsp_url ni de secrets) :
    position, cap de l'objectif et modules effectivement actifs.
    """
    id: int
    name: str
    latitude: float
    longitude: float
    bearing: float = 0.0
    active_modules: List[str] = []

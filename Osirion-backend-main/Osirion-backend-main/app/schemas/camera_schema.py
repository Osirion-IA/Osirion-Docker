# app/schemas/camera_schemas.py
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class CameraCreate(BaseModel):
    cam_name: str
    rtsp_url: str
    location: Optional[str] = None
    is_active: Optional[bool] = True
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
    # NULL pour les caméras HikCentral (URL résolue à la demande, pas stockée).
    rtsp_url: Optional[str] = None
    location: Optional[str]
    is_active: bool

    # Source du flux : "rtsp" (caméra saisie manuellement) ou "hikcentral"
    # (catalogue OpenAPI, URL résolue à la demande). Le Core s'en sert pour
    # décider du transcodage HEVC→H.264 dans le relais MediaMTX.
    source_type: str = "rtsp"
    # Statut HikCentral au dernier sync : 1=en ligne, 2=hors-ligne, None=inconnu/RTSP.
    hik_status: Optional[int] = None

    # Métadonnées géo.
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    bearing: Optional[float] = 0.0

    # Appartenance aux groupes.
    group_ids: List[int] = []

    created_at: datetime


class CameraMapData(BaseModel):
    """Payload allégé pour le composant carte OpenStreetMap / Leaflet.

    Ne contient QUE ce dont la carte a besoin (pas de rtsp_url ni de secrets) :
    position et cap de l'objectif.
    """
    id: int
    name: str
    latitude: float
    longitude: float
    bearing: float = 0.0

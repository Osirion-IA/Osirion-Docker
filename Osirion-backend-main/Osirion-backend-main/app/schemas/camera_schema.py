# app/schemas/camera_schemas.py
from pydantic import BaseModel, Field, model_validator
from typing import Optional, List, Dict
from datetime import datetime


class CameraCreate(BaseModel):
    cam_name: str
    # Obligatoire à la création d'une caméra RTSP manuelle, mais absent lors de
    # l'édition d'une caméra HikCentral (son URL est résolue à la demande).
    # La route d'ajout applique l'obligation métier.
    rtsp_url: Optional[str] = None
    location: Optional[str] = None
    is_active: Optional[bool] = True
    # Métadonnées géospatiales (cartographie). Toutes optionnelles.
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    bearing: Optional[float] = Field(default=0.0, ge=0.0, le=360.0)
    # Politique d'effectif. Les trois champs métier sont soit tous absents
    # (fonction désactivée), soit tous renseignés.
    staffing_max_agents: Optional[int] = Field(default=None, ge=1, le=500)
    staffing_min_agents: Optional[int] = Field(default=None, ge=1, le=500)
    staffing_tolerance_s: int = Field(default=300, ge=30, le=8 * 3600)
    staffing_work_schedule_id: Optional[int] = Field(default=None, ge=1)

    @model_validator(mode="after")
    def _check_staffing(self):
        values = (
            self.staffing_max_agents,
            self.staffing_min_agents,
            self.staffing_work_schedule_id,
        )
        if all(value is None for value in values):
            return self
        if any(value is None for value in values):
            raise ValueError(
                "L'effectif maximum, le minimum requis et le régime horaire "
                "doivent être renseignés ensemble."
            )
        if self.staffing_min_agents > self.staffing_max_agents:
            raise ValueError("L'effectif minimum ne peut pas dépasser l'effectif maximum.")
        return self


# Activation/désactivation d'une caméra sans réenvoyer tout l'objet (notamment
# pas la rtsp_url, qui serait re-chiffrée). Utilisé par PATCH /cameras/{id}/active.
class CameraActiveUpdate(BaseModel):
    is_active: bool


class CameraStaffingSchedule(BaseModel):
    id: int
    name: str
    timezone: str
    segments: Dict[str, List[List[str]]]


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

    # Configuration d'effectif et régime actif résolu pour le Core.
    staffing_max_agents: Optional[int] = None
    staffing_min_agents: Optional[int] = None
    staffing_tolerance_s: int = 300
    staffing_work_schedule_id: Optional[int] = None
    staffing_schedule: Optional[CameraStaffingSchedule] = None

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

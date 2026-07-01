# app/models/camera.py
from sqlmodel import SQLModel, Field, Relationship
from sqlalchemy import Column, Integer, ForeignKey
from typing import Optional, List, TYPE_CHECKING
from datetime import datetime

if TYPE_CHECKING:
    # Import réservé au typage (évite un cycle d'import : camera_groups importe
    # déjà cameras). SQLModel/SQLAlchemy résout la relation via la chaîne
    # "CameraGroup" à la configuration des mappers, une fois les deux modules chargés.
    from app.models.camera_groups import CameraGroup


class CameraGroupLink(SQLModel, table=True):
    """Table d'association N↔N entre `camera` et `cameragroup`.

    Une caméra peut appartenir à plusieurs groupes et un groupe contient
    plusieurs caméras (affectations multiples flexibles). Les deux FK sont en
    ON DELETE CASCADE : supprimer une caméra ou un groupe purge automatiquement
    les liens correspondants (aucune ligne orpheline).
    """
    __tablename__ = "camera_group_link"

    camera_id: Optional[int] = Field(
        default=None,
        sa_column=Column(
            Integer,
            ForeignKey("camera.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )
    group_id: Optional[int] = Field(
        default=None,
        sa_column=Column(
            Integer,
            ForeignKey("cameragroup.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )


class Camera(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    cam_name: str = Field(..., max_length=50)
    rtsp_url: str
    location: Optional[str] = Field(default=None, max_length=100)
    is_active: bool = Field(default=True)

    # ── Drapeaux de module LOCAUX (par caméra) ────────────────────────────────
    # Activent/désactivent un module POUR CETTE caméra spécifiquement. La config
    # EFFECTIVE d'un module = drapeau local ET tous les groupes de la caméra ont
    # ce module actif (cf. app/services/camera_config_service.py). Défaut True →
    # aucune régression : une caméra sans configuration reste pleinement active.
    is_facial_active: bool = Field(default=True)
    is_lpr_active: bool = Field(default=True)

    # ── Métadonnées géospatiales (cartographie OpenStreetMap / Leaflet) ───────
    # Nullable : une caméra non géolocalisée n'apparaît simplement pas sur la carte.
    latitude: Optional[float] = Field(default=None)
    longitude: Optional[float] = Field(default=None)
    # Cap boussole 0–360° de l'objectif : sert à dessiner le cône de champ de
    # vision (field-of-view) sur la carte. Défaut 0.0 (plein nord).
    bearing: Optional[float] = Field(default=0.0)

    created_at: datetime = Field(default_factory=datetime.utcnow)

    # ── Appartenance aux groupes (N↔N) ────────────────────────────────────────
    groups: List["CameraGroup"] = Relationship(
        back_populates="cameras",
        link_model=CameraGroupLink,
    )

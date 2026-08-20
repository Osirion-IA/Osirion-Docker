# app/models/zones.py
"""
Primitives spatiales configurables PAR CAMÉRA (Vision Engine anonyme).

- Zone      : polygone (occupation, file d'attente, attroupement, exclusion).
- CountLine : ligne de comptage (entrées/sorties) = segment A→B + sens « entrée ».

Une zone « ignore » ne produit aucun événement : le Core y jette les détections
avant le tracking (décor trompeur — affiche, écran, reflet dans une vitre).

Coordonnées NORMALISÉES dans [0,1] (repère de la frame) → indépendantes de la
résolution : le même tracé s'applique que la vidéo soit en 640×480 ou 1080p.

`organization_id` : ancrage multi-tenant (non peuplé pour l'instant).
FK camera_id ON DELETE CASCADE : supprimer une caméra purge ses zones/lignes.
"""
from sqlmodel import SQLModel, Field
from sqlalchemy import Column, Integer, ForeignKey, JSON
from typing import Optional, List
from datetime import datetime

# Types de zone (documentent l'usage ; VARCHAR libre côté DB).
ZONE_OCCUPANCY = "occupancy"   # comptage des présents / occupation
ZONE_QUEUE = "queue"           # file d'attente (longueur, temps d'attente)
ZONE_CROWD = "crowd"           # détection d'attroupement (seuil de densité)
ZONE_IGNORE = "ignore"         # EXCLUSION : aucune détection n'y est retenue
ZONE_GENERIC = "generic"


class Zone(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    camera_id: int = Field(
        sa_column=Column(Integer, ForeignKey("camera.id", ondelete="CASCADE"),
                         nullable=False, index=True)
    )
    name: str = Field(..., max_length=100)
    kind: str = Field(default=ZONE_GENERIC, max_length=20)
    # Polygone : liste ordonnée de points [x, y] normalisés dans [0,1] (≥ 3 points).
    polygon: List[List[float]] = Field(sa_column=Column(JSON, nullable=False))
    color: Optional[str] = Field(default=None, max_length=20)
    # Seuil d'occupation (nb de personnes) déclenchant CROWD_DETECTED. None = pas
    # de détection d'attroupement sur cette zone (occupation suivie quand même).
    threshold: Optional[int] = Field(default=None)
    # Délai de CONFIRMATION (s) : une personne n'est comptée dans la zone qu'après
    # y être restée SANS INTERRUPTION pendant ce délai. Filtre les passants et les
    # arrêts brefs, qui gonflaient l'occupation et déclenchaient de faux
    # attroupements. None = repli sur ZONE_MIN_PRESENCE_SECONDS (défaut Core) ;
    # 0 = comptage IMMÉDIAT, à utiliser pour les zones d'intrusion où tout délai
    # serait une régression de sécurité.
    min_presence_s: Optional[float] = Field(default=None)
    organization_id: Optional[int] = Field(default=None, index=True)
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = Field(default=None)


class CountLine(SQLModel, table=True):
    __tablename__ = "count_line"

    id: Optional[int] = Field(default=None, primary_key=True)
    camera_id: int = Field(
        sa_column=Column(Integer, ForeignKey("camera.id", ondelete="CASCADE"),
                         nullable=False, index=True)
    )
    name: str = Field(..., max_length=100)
    # Segment A→B : 2 points [x, y] normalisés dans [0,1].
    point_a: List[float] = Field(sa_column=Column(JSON, nullable=False))
    point_b: List[float] = Field(sa_column=Column(JSON, nullable=False))
    # Sens « entrée » : côté du segment (signe du produit vectoriel AB × AP) compté
    # comme une entrée. "positive" | "negative" — l'UI pose la flèche ; le comptage
    # effectif (franchissement) sera implémenté par l'Event Engine (Phase C).
    in_direction: str = Field(default="positive", max_length=10)
    organization_id: Optional[int] = Field(default=None, index=True)
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = Field(default=None)

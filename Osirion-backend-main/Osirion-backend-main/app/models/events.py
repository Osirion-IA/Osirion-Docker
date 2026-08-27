# app/models/event.py
from sqlmodel import SQLModel, Field
from sqlalchemy import Column, JSON, Index
from typing import Optional, Dict, Any
from datetime import datetime

# Types d'événements supportés (event_type est un VARCHAR libre — ces constantes
# documentent les valeurs valides et évitent les fautes de frappe côté code).
EVENT_ENTRY = "ENTRY"
EVENT_EXIT = "EXIT"
EVENT_DETECTION = "DETECTION"
# Événements spatiaux/comportementaux produits par l'Event Engine (Phase C).
EVENT_ZONE_OCCUPANCY_CHANGED = "ZONE_OCCUPANCY_CHANGED"
EVENT_CROWD_DETECTED = "CROWD_DETECTED"
EVENT_LINE_CROSSED = "LINE_CROSSED"
EVENT_ZONE_DWELL = "ZONE_DWELL"
# ── Présence aux postes (zones `presence` + régime horaire) ──────────────────
# Deux événements complémentaires, émis UNIQUEMENT pendant les créneaux
# travaillés du régime (pas de bruit la nuit ni le week-end) :
#   POST_VACANT  : signal TEMPS RÉEL — le poste est vide depuis la tolérance.
#                  C'est lui qu'une règle d'alerte doit écouter.
#   POST_ABSENCE : épisode CLOS, avec sa durée totale (`absence_s`). C'est lui
#                  qui sert à cumuler le temps d'absence d'une journée.
# Un épisode se clôt au retour de l'agent OU à la fin du créneau de travail.
EVENT_POST_VACANT = "POST_VACANT"
EVENT_POST_ABSENCE = "POST_ABSENCE"
PRESENCE_SCHEMA_VERSION = 2
PRESENCE_DATA_RELIABLE = "reliable"
PRESENCE_DATA_ARCHIVED = "archived"
# ── Effectif global d'agents par caméra ─────────────────────────────────────
# STAFFING_LOW est le signal temps réel (règles/alertes), après maintien sous le
# minimum pendant la tolérance. STAFFING_RECOVERED clôt l'épisode et porte sa
# durée totale pour l'analytique.
EVENT_STAFFING_LOW = "STAFFING_LOW"
EVENT_STAFFING_RECOVERED = "STAFFING_RECOVERED"

class Event(SQLModel, table=True):
    # Deux profils d'accès distincts sur `event` :
    #  - par caméra + type + période (footfall d'une caméra, by-camera) → index
    #    couvrant qui COMMENCE par camera_id ;
    #  - par type + période SANS caméra (occupation/files/summary/insights, qui
    #    agrègent tout le parc) → l'index précédent est INUTILISABLE (camera_id en
    #    tête), d'où un full scan de `event`. Le second index (event_type,
    #    timestamp) sert exactement ces requêtes, y compris l'ORDER BY timestamp.
    __table_args__ = (
        Index("ix_event_camera_type_ts", "camera_id", "event_type", "timestamp"),
        Index("ix_event_type_ts", "event_type", "timestamp"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    camera_id: int = Field(foreign_key="camera.id")
    event_type: str = Field(..., max_length=30)
    confidence: Optional[float] = None
    snapshot_url: Optional[str] = None
    # Contexte structuré (zone_id, zone_name, count, direction, line_id…). JSON
    # libre → aucun couplage au cycle de vie des zones/lignes (un événement
    # historique survit à la suppression de sa zone).
    meta: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON))

    timestamp: datetime = Field(default_factory=datetime.utcnow)

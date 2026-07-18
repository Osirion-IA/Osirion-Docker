# app/models/event.py
from sqlmodel import SQLModel, Field
from sqlalchemy import Column, JSON
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

class Event(SQLModel, table=True):
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

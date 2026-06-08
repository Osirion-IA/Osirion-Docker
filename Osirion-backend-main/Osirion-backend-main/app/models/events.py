# app/models/event.py
from sqlmodel import SQLModel, Field, Relationship
from typing import Optional
from datetime import datetime

# Types d'événements supportés (event_type est un VARCHAR libre — ces constantes
# documentent les valeurs valides et évitent les fautes de frappe côté code).
EVENT_RECOGNITION = "RECOGNITION"            # reconnaissance faciale (personne connue)
EVENT_ENTRY = "ENTRY"
EVENT_EXIT = "EXIT"
EVENT_DETECTION = "DETECTION"
EVENT_PLATE_RECOGNITION = "PLATE_RECOGNITION"  # reconnaissance de plaque (LPR/ANPR)
EVENT_UNKNOWN_FACE = "UNKNOWN_FACE"          # visage détecté mais NON reconnu (person_id NULL)

class Event(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    camera_id: int = Field(foreign_key="camera.id")
    person_id: Optional[int] = Field(default=None, foreign_key="people.id")
    event_type: str = Field(..., max_length=30)
    confidence: Optional[float] = None
    snapshot_url: Optional[str] = None

    # ── LPR / ANPR ──────────────────────────────────────────────────────────
    # Texte de plaque lu par l'OCR (normalisé). Renseigné pour event_type=PLATE_RECOGNITION.
    plate_text_detected: Optional[str] = Field(default=None, max_length=20)
    # Véhicule connu correspondant (None si plaque inconnue / non enregistrée).
    vehicle_id: Optional[int] = Field(default=None, foreign_key="vehicle.id")

    timestamp: datetime = Field(default_factory=datetime.utcnow)

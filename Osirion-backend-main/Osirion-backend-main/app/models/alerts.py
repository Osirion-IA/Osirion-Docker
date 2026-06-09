# app/models/alerts.py
"""
Modèle Alert — centre d'alertes (hits blacklist).

Une alerte est créée AUTOMATIQUEMENT côté backend lorsqu'un événement de
détection concerne une entité blacklistée (personne sur liste de surveillance
OU plaque blacklistée). C'est un simple enregistrement traçable, AVEC un
workflow (new → acknowledged → resolved).

⚠️ Important : la création d'une alerte n'envoie JAMAIS de notification (email/
webhook). L'envoi est déclenché EXCLUSIVEMENT par un utilisateur via
POST /alerts/{id}/notify (cf. notification_service).
"""
from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import datetime

# Statuts du workflow d'alerte.
ALERT_NEW = "new"
ALERT_ACKNOWLEDGED = "acknowledged"
ALERT_RESOLVED = "resolved"

# Types d'alerte.
ALERT_KIND_PERSON = "person"
ALERT_KIND_PLATE = "plate"


class Alert(SQLModel, table=True):
    __tablename__ = "alert"

    id: Optional[int] = Field(default=None, primary_key=True)

    # Lien vers l'événement source (snapshot, caméra, timestamp d'origine).
    event_id: Optional[int] = Field(default=None, foreign_key="event.id")

    kind: str = Field(..., max_length=20)             # "person" | "plate"
    label: str = Field(..., max_length=255)           # nom de la personne ou texte de plaque
    reason: Optional[str] = Field(default=None, max_length=255)  # motif blacklist

    camera_id: Optional[int] = Field(default=None)
    person_id: Optional[int] = Field(default=None, foreign_key="people.id")
    vehicle_id: Optional[int] = Field(default=None, foreign_key="vehicle.id")
    snapshot_url: Optional[str] = Field(default=None, max_length=255)

    # Workflow : new → acknowledged → resolved.
    status: str = Field(default=ALERT_NEW, max_length=20, index=True)
    acknowledged_at: Optional[datetime] = Field(default=None)
    acknowledged_by: Optional[int] = Field(default=None)   # user.id qui a acquitté

    # Notification MANUELLE (jamais automatique).
    notified_at: Optional[datetime] = Field(default=None)
    notified_channel: Optional[str] = Field(default=None, max_length=40)

    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)

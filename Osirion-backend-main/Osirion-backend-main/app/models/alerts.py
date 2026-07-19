# app/models/alerts.py
"""
Modèle Alert — centre d'alertes (hits blacklist).

Une alerte est un enregistrement traçable (workflow new → acknowledged →
resolved) émis quand une règle de décision se déclenche (ex. seuil d'occupation,
présence hors horaires). Alimentée par le moteur de règles (à venir) ;
l'infrastructure (workflow + notifications) est ici.

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

# Sévérités (reprises de la règle qui a déclenché l'alerte).
SEV_INFO = "info"
SEV_WARNING = "warning"
SEV_CRITICAL = "critical"

# Types d'alerte (libre : ex. "crowd", "intrusion", "occupancy"…).


class Alert(SQLModel, table=True):
    __tablename__ = "alert"

    id: Optional[int] = Field(default=None, primary_key=True)

    # Lien vers l'événement source (snapshot, caméra, timestamp d'origine).
    event_id: Optional[int] = Field(default=None, foreign_key="event.id")

    kind: str = Field(..., max_length=20)             # "crowd" | "intrusion" | …
    severity: str = Field(default="warning", max_length=20)  # info | warning | critical
    label: str = Field(..., max_length=255)           # libellé de l'alerte
    reason: Optional[str] = Field(default=None, max_length=255)  # motif / détail

    camera_id: Optional[int] = Field(default=None)
    snapshot_url: Optional[str] = Field(default=None, max_length=255)

    # Workflow : new → acknowledged → resolved.
    status: str = Field(default=ALERT_NEW, max_length=20, index=True)
    acknowledged_at: Optional[datetime] = Field(default=None)
    acknowledged_by: Optional[int] = Field(default=None)   # user.id qui a acquitté

    # Notification MANUELLE (jamais automatique).
    notified_at: Optional[datetime] = Field(default=None)
    notified_channel: Optional[str] = Field(default=None, max_length=40)

    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)

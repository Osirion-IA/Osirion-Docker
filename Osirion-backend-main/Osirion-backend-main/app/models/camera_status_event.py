# app/models/camera_status_event.py
"""
Historique de CONNECTIVITÉ des caméras (transitions d'état).

La santé caméra est calculée en TEMPS RÉEL par le Core (éphémère, perdue au
redémarrage). Ce modèle PERSISTE chaque CHANGEMENT d'état (online → offline,
reconnexions, etc.) pour reconstituer un historique : pertes de signal,
déconnexions, temps hors-ligne, disponibilité (uptime), MTBF…

Alimenté par un poller backend (services.camera_status_recorder) qui interroge la
santé du Core et n'écrit QUE sur transition (pas de spam). Pas de FK vers camera :
c'est un journal opérationnel qui doit survivre à la suppression d'une caméra.
"""
from sqlmodel import SQLModel, Field
from sqlalchemy import Index
from typing import Optional
from datetime import datetime

# États (repris de la santé Core).
CAM_ONLINE = "online"
CAM_OFFLINE = "offline"
CAM_CONNECTING = "connecting"
CAM_STALLED = "stalled"       # flux ouvert mais plus de frames fraîches
CAM_STOPPED = "stopped"       # threads arrêtés (caméra désactivée)


class CameraStatusEvent(SQLModel, table=True):
    __tablename__ = "camera_status_event"
    __table_args__ = (
        Index("ix_camstatus_cam_ts", "camera_id", "timestamp"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    camera_id: int = Field(index=True)
    status: str = Field(max_length=20)
    prev_status: Optional[str] = Field(default=None, max_length=20)
    reconnection_attempts: Optional[int] = Field(default=None)
    reason: Optional[str] = Field(default=None, max_length=255)
    timestamp: datetime = Field(default_factory=datetime.utcnow, index=True)

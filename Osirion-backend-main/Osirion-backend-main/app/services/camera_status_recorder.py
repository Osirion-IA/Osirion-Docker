# app/services/camera_status_recorder.py
"""
Enregistreur de statut caméra (thread de fond).

Interroge la santé temps réel du Core (CORE_URL/api/cameras/health) toutes les
CAMERA_STATUS_POLL_SECONDS et PERSISTE chaque CHANGEMENT d'état dans
`camera_status_event` (jamais de doublon : on n'écrit que sur transition). Au
démarrage, recharge le dernier statut connu depuis la base → pas d'événement
« baseline » parasite après un simple rechargement du backend.

Best-effort : Core injoignable → on saute ce cycle, jamais fatal.
"""
import logging
import threading
import time
from datetime import datetime

import requests
from sqlmodel import Session, text

from app.config import settings
from app.database import engine
from app.models.camera_status_event import CameraStatusEvent

logger = logging.getLogger(__name__)

_started = False
_start_lock = threading.Lock()
_thread: "threading.Thread | None" = None
_last_status: dict = {}   # cam_id -> dernier statut connu


def is_running() -> bool:
    return _thread is not None and _thread.is_alive()


def _load_last_status() -> None:
    """Recharge le dernier statut connu par caméra (DISTINCT ON, efficace)."""
    try:
        with Session(engine) as session:
            rows = session.exec(text(
                "SELECT DISTINCT ON (camera_id) camera_id, status "
                "FROM camera_status_event ORDER BY camera_id, timestamp DESC"
            )).all()
        for cam_id, status in rows:
            _last_status[cam_id] = status
    except Exception:
        logger.debug("[camstatus] pré-chargement du dernier statut impossible", exc_info=True)


def _poll_once() -> None:
    url = settings.CORE_URL.rstrip("/") + "/api/cameras/health"
    r = requests.get(url, timeout=8)
    r.raise_for_status()
    cams = r.json().get("cameras", [])
    now = datetime.utcnow()
    changed = 0
    with Session(engine) as session:
        for c in cams:
            cid = c.get("id")
            status = c.get("state")
            if cid is None or not status:
                continue
            prev = _last_status.get(cid)
            if prev == status:
                continue
            session.add(CameraStatusEvent(
                camera_id=cid, status=status, prev_status=prev,
                reconnection_attempts=c.get("reconnection_attempts"),
                timestamp=now,
            ))
            _last_status[cid] = status
            changed += 1
        if changed:
            session.commit()
            logger.debug("[camstatus] %d transition(s) enregistrée(s).", changed)


def _loop(interval_s: int) -> None:
    time.sleep(min(interval_s, 20))   # laisse le Core démarrer
    while True:
        try:
            _poll_once()
        except Exception:
            logger.debug("[camstatus] poll échoué (Core injoignable ?)", exc_info=True)
        time.sleep(interval_s)


def start() -> None:
    """Démarre (une seule fois par processus) l'enregistreur de statut caméra."""
    global _started, _thread
    if not getattr(settings, "CAMERA_STATUS_RECORDER_ENABLED", True):
        return
    interval = max(5, int(getattr(settings, "CAMERA_STATUS_POLL_SECONDS", 15)))
    with _start_lock:
        if _started:
            return
        _started = True
        _load_last_status()
        _thread = threading.Thread(target=_loop, args=(interval,), daemon=True, name="cam-status")
        _thread.start()
    logger.info("[camstatus] enregistreur de statut caméra activé (%d s).", interval)

# app/services/hikcentral_scheduler.py
"""
Synchronisation PÉRIODIQUE du catalogue HikCentral (thread de fond, sans dépendance).

Un daemon thread rejoue sync_catalog toutes les HIK_SYNC_INTERVAL_MINUTES : les
caméras / agences ajoutées côté HikCentral apparaissent automatiquement dans le
catalogue (elles restent NON traitées jusqu'à leur 1re configuration — activation
paresseuse). Best-effort : toute erreur est logguée sans jamais tuer le thread.
0 min = désactivé (synchro manuelle seulement).
"""
import logging
import threading
import time

from sqlmodel import Session

from app.config import settings
from app.database import engine
from app.services import hikcentral_connector as hik
from app.services.hikcentral_sync import sync_catalog

logger = logging.getLogger(__name__)

_started = False
_start_lock = threading.Lock()
_thread: threading.Thread | None = None


def is_running() -> bool:
    """Le thread de synchro périodique est-il actif ?"""
    return _thread is not None and _thread.is_alive()


def _loop(interval_s: int) -> None:
    time.sleep(min(interval_s, 60))  # laisse le backend finir de démarrer
    while True:
        try:
            if hik.is_configured():
                with Session(engine) as session:
                    stats = sync_catalog(session)
                logger.info("[hik] synchro périodique : %s", stats)
        except Exception:  # noqa: BLE001 — jamais fatal pour le thread
            logger.warning("[hik] synchro périodique en échec (réessai au prochain cycle).", exc_info=True)
        time.sleep(interval_s)


def start_periodic_sync() -> None:
    """Démarre (une seule fois par processus) le thread de synchro périodique."""
    global _started
    minutes = getattr(settings, "HIK_SYNC_INTERVAL_MINUTES", 0) or 0
    if minutes <= 0:
        return
    if not hik.is_configured():
        logger.info("[hik] synchro périodique désactivée (connecteur non configuré).")
        return
    global _thread
    with _start_lock:
        if _started:
            return
        _started = True
        _thread = threading.Thread(target=_loop, args=(minutes * 60,), daemon=True, name="hik-sync")
        _thread.start()
    logger.info("[hik] synchro périodique activée (toutes les %d min).", minutes)

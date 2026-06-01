# core/runtime_control.py
"""
État de contrôle runtime partagé entre les threads.

Permet à l'interface (frontend → endpoint Flask /api/lpr/toggle) d'activer ou
désactiver dynamiquement le pipeline LPR sans redémarrer le Core, et aux threads
de traitement (TrackingProcessor) de lire cet état de manière thread-safe.
"""
import threading
from utils.logger import get_logger

logger = get_logger(__name__)


class RuntimeControl:
    """Drapeaux de contrôle modifiables à chaud, protégés par un verrou."""

    def __init__(self, lpr_enabled: bool = False):
        self._lock = threading.Lock()
        self._lpr_enabled = bool(lpr_enabled)

    @property
    def lpr_enabled(self) -> bool:
        with self._lock:
            return self._lpr_enabled

    def set_lpr(self, enabled: bool) -> bool:
        """Active/désactive le LPR. Retourne le nouvel état."""
        with self._lock:
            self._lpr_enabled = bool(enabled)
            logger.info(f"[runtime] LPR {'activé' if self._lpr_enabled else 'désactivé'} (toggle)")
            return self._lpr_enabled

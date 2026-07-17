# core/runtime_control.py
"""
État de contrôle runtime partagé entre les threads.

Permet à l'interface (frontend → endpoints Flask /api/face/toggle,
/api/unknown-face/toggle) d'activer ou désactiver dynamiquement des pipelines
sans redémarrer le Core, et aux threads de traitement (TrackingProcessor) de
lire cet état de manière thread-safe.
"""
import threading
from utils.logger import get_logger

logger = get_logger(__name__)


class RuntimeControl:
    """Drapeaux de contrôle modifiables à chaud, protégés par un verrou."""

    def __init__(self, unknown_face_event_enabled: bool = False,
                 face_recognition_enabled: bool = True):
        self._lock = threading.Lock()
        # Émission d'un événement distinct (UNKNOWN_FACE) pour les visages détectés
        # mais NON reconnus. Opt-in, indépendant du facial standard.
        self._unknown_face_event_enabled = bool(unknown_face_event_enabled)
        # Pipeline de reconnaissance faciale (PRINCIPAL). DÉFAUT True : il tourne
        # tant qu'on ne le coupe pas explicitement → aucune régression au démarrage.
        self._face_recognition_enabled = bool(face_recognition_enabled)

    @property
    def unknown_face_event_enabled(self) -> bool:
        with self._lock:
            return self._unknown_face_event_enabled

    def set_unknown_face_event(self, enabled: bool) -> bool:
        """Active/désactive l'événement « visage non reconnu ». Retourne le nouvel état."""
        with self._lock:
            self._unknown_face_event_enabled = bool(enabled)
            logger.info(
                f"[runtime] Événement visage non reconnu "
                f"{'activé' if self._unknown_face_event_enabled else 'désactivé'} (toggle)"
            )
            return self._unknown_face_event_enabled

    @property
    def face_recognition_enabled(self) -> bool:
        with self._lock:
            return self._face_recognition_enabled

    def set_face_recognition(self, enabled: bool) -> bool:
        """Active/désactive la reconnaissance faciale à chaud. Retourne le nouvel état."""
        with self._lock:
            self._face_recognition_enabled = bool(enabled)
            logger.info(
                f"[runtime] Reconnaissance faciale "
                f"{'activée' if self._face_recognition_enabled else 'désactivée'} (toggle)"
            )
            return self._face_recognition_enabled

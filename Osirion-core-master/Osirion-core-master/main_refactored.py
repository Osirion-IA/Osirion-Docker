# main_refactored.py
"""
Point d'entrée de l'application de surveillance multi-caméras
Version modulaire et refactorisée
"""

# ── Silence du bruit de logs tiers — DOIT précéder tout import de cv2/insightface/
#    ultralytics (les variables d'env sont lues à l'import de ces libs). ──────────
import os as _os
import warnings as _warnings

# ffmpeg/OpenCV : erreurs de décodage H264 sur perte de paquets RTSP (cosmétique,
# spammé « [h264 @ …] error while decoding MB … »). 8 = niveau « fatal » only.
_os.environ.setdefault("OPENCV_FFMPEG_LOGLEVEL", "8")
# Ultralytics : évite le repli « ~/.config/Ultralytics non inscriptible ».
_os.environ.setdefault("YOLO_CONFIG_DIR", "/tmp/Ultralytics")
# insightface (face_align) émet un FutureWarning `estimate` PAR VISAGE → on le tait.
_warnings.filterwarnings("ignore", category=FutureWarning, module="insightface")
# albumentations (tiré par insightface) tente un check de version en ligne au boot
# → échoue hors-ligne (« Temporary failure in name resolution »). On le désactive.
_os.environ.setdefault("NO_ALBUMENTATIONS_UPDATE", "1")

import signal
import sys

from config import settings
from core.surveillance_system import SurveillanceSystem
from utils.logger import setup_logging, get_logger

# Initialiser le système de logging
setup_logging(
    log_level=settings.LOG_LEVEL,
    log_dir=settings.LOG_DIR,
    enable_json=settings.ENABLE_JSON_LOGS,
    enable_console=settings.ENABLE_CONSOLE_LOGS,
    max_bytes=settings.LOG_MAX_BYTES,
    backup_count=settings.LOG_BACKUP_COUNT
)

logger = get_logger(__name__)


def main():
    """Point d'entrée principal de l'application"""
    import time

    logger.info("Démarrage d'Osirion-Core...")

    system = SurveillanceSystem(config=settings)

    # Docker envoie SIGTERM avant SIGKILL — on le convertit en SystemExit
    # pour que le bloc finally s'exécute et arrête proprement les threads.
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))

    # ── Recherche d'embeddings LOCALE (réplique FAISS dans le Core) — OPT-IN ──
    # Active uniquement si FAISS_LOCAL=true. Sinon : comportement inchangé
    # (recherche via HTTP backend). Tout échec ici → repli HTTP automatique.
    if getattr(settings, "FAISS_LOCAL", False):
        try:
            from core import face_index
            ready = face_index.init(
                reconcile_interval=getattr(settings, "FAISS_LOCAL_RECONCILE_SECONDS", 15)
            )
            logger.info(
                "[face_index] recherche locale %s",
                "ACTIVE" if ready else "en repli HTTP (chargement initial KO, réessai auto)",
            )
        except Exception as e:
            logger.error("[face_index] init impossible (repli HTTP) : %s", e)

    # Démarrer le serveur web en premier pour que le healthcheck réponde
    # même si aucune caméra n'est encore configurée.
    if settings.ENABLE_WEB_STREAMING:
        system.enable_web_streaming()

    # Lancer le système (ne plante plus si 0 caméra).
    system.run()

    try:
        while True:
            time.sleep(1)

    except (KeyboardInterrupt, SystemExit):
        logger.info("Arrêt demandé")

    finally:
        system.stop()
        if getattr(settings, "FAISS_LOCAL", False):
            try:
                from core import face_index
                face_index.stop()
            except Exception:
                pass


if __name__ == "__main__":
    main()

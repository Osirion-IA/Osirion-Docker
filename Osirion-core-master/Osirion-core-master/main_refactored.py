# main_refactored.py
"""
Point d'entrée de l'application de surveillance multi-caméras
Version modulaire et refactorisée
"""

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


if __name__ == "__main__":
    main()

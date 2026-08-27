# services/zones_fetching_service.py
"""
Récupération des zones (polygones) et lignes de comptage d'une caméra depuis le
backend (GET /zones, /zones/lines). Utilisé par l'Event Engine, rafraîchi
périodiquement DANS UN THREAD DÉDIÉ (jamais sur le thread caméra).
"""
from typing import List, Dict, Any, Optional

from utils.api_client import request_with_auth
from utils.logger import get_logger

logger = get_logger(__name__)


def _fetch(path: str, camera_id: int) -> Optional[List[Dict[str, Any]]]:
    try:
        # Ré-authentification + retry automatiques sur 401/coupure réseau.
        r = request_with_auth("GET", path, params={"camera_id": camera_id}, timeout=10)
        r.raise_for_status()
        data = r.json()
        return data if isinstance(data, list) else []
    except Exception as e:
        logger.debug(f"[zones] récupération {path} (cam {camera_id}) échouée : {e}")
        # None = appel en échec ; [] = appel réussi mais aucune configuration.
        # Cette distinction empêche le Core d'effacer sa configuration en mémoire
        # pendant une coupure temporaire du backend.
        return None


def fetch_zones(camera_id: int) -> Optional[List[Dict[str, Any]]]:
    return _fetch("/zones/", camera_id)


def fetch_lines(camera_id: int) -> Optional[List[Dict[str, Any]]]:
    return _fetch("/zones/lines", camera_id)

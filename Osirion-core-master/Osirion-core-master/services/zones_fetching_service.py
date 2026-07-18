# services/zones_fetching_service.py
"""
Récupération des zones (polygones) et lignes de comptage d'une caméra depuis le
backend (GET /zones, /zones/lines). Utilisé par l'Event Engine, rafraîchi
périodiquement DANS UN THREAD DÉDIÉ (jamais sur le thread caméra).
"""
import requests
from typing import List, Dict, Any

from utils.auth_utils import get_auth_headers, API_URL
from utils.logger import get_logger

logger = get_logger(__name__)


def _fetch(path: str, camera_id: int) -> List[Dict[str, Any]]:
    try:
        r = requests.get(
            f"{API_URL}{path}",
            params={"camera_id": camera_id},
            headers=get_auth_headers(),
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()
        return data if isinstance(data, list) else []
    except Exception as e:
        logger.debug(f"[zones] récupération {path} (cam {camera_id}) échouée : {e}")
        return []


def fetch_zones(camera_id: int) -> List[Dict[str, Any]]:
    return _fetch("/zones/", camera_id)


def fetch_lines(camera_id: int) -> List[Dict[str, Any]]:
    return _fetch("/zones/lines", camera_id)

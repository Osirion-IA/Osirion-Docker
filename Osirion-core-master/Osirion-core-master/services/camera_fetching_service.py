import requests
from typing import List, Dict, Any
from utils.api_client import request_with_auth
from utils.logger import get_logger

logger = get_logger(__name__)

def fetch_camera_list() -> List[Dict[str, Any]]:
    try:
        # request_with_auth se ré-authentifie et réessaie automatiquement sur 401
        # (token expiré) ou coupure réseau → le Core ne « décroche » plus.
        response = request_with_auth("GET", "/cameras/", timeout=10)
        response.raise_for_status()

        data = response.json()

        # L'API renvoie directement une liste.
        if isinstance(data, list):
            cameras = data
        else:
            cameras = data.get("cameras", [])

        logger.info(f"{len(cameras)} caméra(s) récupérée(s) depuis l'API")
        return cameras

    except requests.exceptions.HTTPError as e:
        status_code = e.response.status_code if e.response else 'unknown'
        logger.error(f"Erreur HTTP {status_code} lors de la récupération des caméras")
        return []
    except Exception as e:
        logger.error(f"Erreur réseau ou parsing JSON : {e}")
        return []

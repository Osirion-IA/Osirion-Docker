import requests
from utils.auth_utils import get_auth_headers, API_URL
from typing import List, Dict, Any
from utils.logger import get_logger

logger = get_logger(__name__)
URL = f"{API_URL}/cameras/"

def fetch_camera_list() -> List[Dict[str, Any]]:
    try:
        response = requests.get(URL, headers=get_auth_headers(), timeout=10)
        response.raise_for_status()
        
        data = response.json()
        
        # Correction ici : l'API renvoie directement une liste
        if isinstance(data, list):
            cameras = data
        else:
            cameras = data.get("cameras", [])
            
        logger.info(f"{len(cameras)} caméra(s) récupérée(s) depuis l'API")
        return cameras

    except requests.exceptions.HTTPError as e:
        status_code = e.response.status_code if e.response else 'unknown'
        logger.error(f"Erreur HTTP {status_code} lors de la récupération des caméras")
        if status_code == 401:
            logger.info("Tentative de rafraîchissement du token...")
            # Tu peux appeler une fonction de refresh ici si besoin
        return []
    except Exception as e:
        logger.error(f"Erreur réseau ou parsing JSON : {e}")
        return []
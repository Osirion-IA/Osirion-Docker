# services/hik_stream_resolver.py
"""
Résolution des URLs de flux HikCentral pour les caméras du catalogue.

Les caméras `source_type="hikcentral"` n'ont PAS de rtsp_url stockée : leur URL
RTSP standard (rtsp_s) est résolue À LA DEMANDE par le backend (qui seul détient
les credentials AK/SK HikCentral). Le Core la récupère via
`GET /hikcentral/stream-url?cam=<id>` avant de (re)créer le relais MediaMTX.

Le cache TTL vit CÔTÉ BACKEND (voir hikcentral_connector.resolve_stream_url) :
HikCentral n'est donc pas sollicité à chaque cycle de supervision, même si le Core
appelle cet endpoint à chaque réconciliation. Best-effort : toute erreur renvoie
None (la caméra est simplement ignorée ce cycle-ci, réessayée au suivant).
"""
from typing import Optional

from utils.api_client import request_with_auth
from utils.logger import get_logger

logger = get_logger(__name__)


def resolve_stream_url(cam_id: int, refresh: bool = False) -> Optional[str]:
    """URL RTSP standard fraîche pour une caméra HikCentral, ou None si indisponible."""
    try:
        # request_with_auth gère la ré-authentification/retry sur 401 (cf. api_client).
        resp = request_with_auth(
            "GET", "/hikcentral/stream-url",
            params={"cam": cam_id, "refresh": str(bool(refresh)).lower()},
            timeout=30,  # 1re résolution HikCentral parfois lente (démarrage SMS)
        )
        if resp.status_code != 200:
            logger.warning(
                f"Résolution URL HikCentral caméra {cam_id} : HTTP {resp.status_code} "
                f"({resp.text[:200]})"
            )
            return None
        url = resp.json().get("url")
        if not url:
            logger.warning(f"Résolution URL HikCentral caméra {cam_id} : réponse sans url.")
            return None
        return url
    except Exception as e:  # noqa: BLE001 — best-effort, jamais bloquant
        logger.warning(f"Résolution URL HikCentral caméra {cam_id} échouée : {e}")
        return None

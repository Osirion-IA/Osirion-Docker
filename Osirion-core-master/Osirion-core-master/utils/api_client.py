# utils/api_client.py
"""
Client HTTP résilient vers le backend (auto-réparation d'authentification).

`request_with_auth()` enveloppe requests.request() :
  1) 1er essai avec le token/clé courant ;
  2) sur 401 → refresh FORCÉ du token puis retry (en mode clé de service, la clé
     est renvoyée telle quelle → un 401 signifie une mauvaise clé, borné par retries) ;
  3) sur erreur réseau → retry avec back-off borné.

But : le Core ne « décroche » jamais du backend sur une simple expiration de token
ou une coupure réseau transitoire. À utiliser partout où le Core appelle le backend.
"""
import time
import requests

from utils.auth_utils import get_auth_headers, API_URL
from utils.logger import get_logger

logger = get_logger(__name__)

_MAX_BACKOFF = 5.0


def request_with_auth(method: str, path: str, *, retries: int = 2,
                      timeout: float = 10.0, headers: dict | None = None,
                      **kwargs) -> requests.Response:
    """Requête authentifiée avec refresh-sur-401 et retry réseau.

    `path` : chemin relatif ("/cameras/") — préfixé par API_URL — ou URL absolue.
    Renvoie la Response (même un 401 final, à l'appelant de faire raise_for_status).
    Lève l'exception réseau si tous les essais échouent.
    """
    url = path if path.startswith("http") else f"{API_URL}{path}"
    base_headers = headers or {}
    resp = None
    for attempt in range(retries + 1):
        # 1er essai : token courant ; essais suivants : refresh forcé (mode JWT).
        auth = get_auth_headers(force=(attempt > 0))
        try:
            resp = requests.request(method, url, headers={**base_headers, **auth},
                                    timeout=timeout, **kwargs)
        except requests.RequestException as exc:
            if attempt >= retries:
                logger.warning(f"[api] {method} {path} : échec réseau définitif ({exc})")
                raise
            time.sleep(min(2 ** attempt, _MAX_BACKOFF))
            continue

        if resp.status_code == 401 and attempt < retries:
            logger.warning(f"[api] 401 sur {method} {path} — ré-authentification + retry")
            continue
        return resp

    return resp

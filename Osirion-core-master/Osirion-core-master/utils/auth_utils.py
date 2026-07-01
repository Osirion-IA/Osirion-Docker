# auth.py
import base64
import json
import threading
import requests
import os
import time
from dotenv import load_dotenv
from utils.logger import get_logger

logger = get_logger(__name__)
load_dotenv()

API_URL = os.getenv("API_URL").rstrip("/")
EMAIL = os.getenv("AUTH_EMAIL")
PASSWORD = os.getenv("AUTH_PASSWORD")

if not all([API_URL, EMAIL, PASSWORD]):
    raise ValueError("Variables manquantes dans .env : API_URL, AUTH_EMAIL, AUTH_PASSWORD")

# ── État partagé protégé par _lock ──────────────────────────────────────────
# Le Core est massivement multi-thread (threads caméra, workers reconnaissance,
# poll blacklist, fetch caméras, workers plaques…). TOUS lisent/écrivent ces
# globals → il FAUT un verrou, sinon à l'expiration du token plusieurs threads
# tentent un refresh concurrent avec un refresh_token que le backend RÉVOQUE à la
# rotation → 401 en cascade. Le verrou sérialise et COALESCE les refresh.
_lock = threading.RLock()
_access_token: str | None = None
_refresh_token: str | None = None
_access_exp: float = 0.0        # epoch (s) d'expiration de l'access token (lu dans le JWT)
_last_refresh: float = 0.0      # monotonic() du dernier refresh/login (coalescing 401)

# Rafraîchir l'access token CETTE MARGE avant son expiration réelle → aucune
# fenêtre où un token expiré circule (la cause des 401 périodiques toutes les 30 min).
_REFRESH_MARGIN = 90.0          # s avant exp
# Deux 401 concurrents ne déclenchent qu'UN refresh : dans cette fenêtre après un
# refresh réussi, un force-refresh renvoie directement le token déjà rafraîchi.
_COALESCE_WINDOW = 10.0         # s


def _token_exp(token: str | None) -> float:
    """Lit le champ `exp` (epoch s) du JWT SANS vérifier la signature (on ne fait
    que planifier le refresh). Retourne 0.0 si illisible → refresh immédiat."""
    if not token:
        return 0.0
    try:
        payload_b64 = token.split(".")[1]
        payload_b64 += "=" * (-len(payload_b64) % 4)   # padding base64url
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        return float(payload.get("exp", 0.0))
    except Exception:
        return 0.0


def _store_tokens(data: dict) -> None:
    """Mémorise les tokens d'une réponse login/refresh. À APPELER SOUS _lock."""
    global _access_token, _refresh_token, _access_exp, _last_refresh
    _access_token = data.get("access_token") or data.get("token")
    new_refresh = data.get("refresh_token") or data.get("refreshToken")
    if new_refresh:
        _refresh_token = new_refresh
    if not _access_token:
        raise ValueError("access_token non reçu")
    _access_exp = _token_exp(_access_token)
    _last_refresh = time.monotonic()


def _perform_login() -> None:
    """Login complet (email/password). À APPELER SOUS _lock."""
    logger.info("Connexion à l'API en cours...")
    resp = requests.post(
        f"{API_URL}/auth/login",
        json={"email": EMAIL, "password": PASSWORD},
        timeout=15,
    )
    if resp.status_code != 200:
        raise ConnectionError(f"Login échoué ({resp.status_code}) : {resp.text}")
    _store_tokens(resp.json())
    logger.info("Connexion réussie à l'API")


def _do_refresh() -> None:
    """Rafraîchit via /auth/refresh, repli sur login complet. À APPELER SOUS _lock."""
    if not _refresh_token:
        _perform_login()
        return
    try:
        resp = requests.post(
            f"{API_URL}/auth/refresh",
            json={"refresh_token": _refresh_token},
            timeout=10,
        )
    except requests.RequestException as exc:
        logger.warning(f"Refresh réseau KO ({exc}) — reconnexion complète")
        _perform_login()
        return
    if resp.status_code == 200:
        _store_tokens(resp.json())
        logger.debug("Token rafraîchi (proactif/sur-401)")
    else:
        # Refresh token expiré OU déjà révoqué par une rotation concurrente → login.
        logger.warning(f"Refresh refusé (HTTP {resp.status_code}) — reconnexion complète")
        _perform_login()


def get_bearer_token(force: bool = False) -> str:
    """Retourne un access token VALIDE (thread-safe).

    - force=False : refresh PROACTIF si le token expire dans moins de _REFRESH_MARGIN.
    - force=True  : refresh immédiat (appelé par un service qui a réellement reçu un
      401), mais COALESCÉ — si un autre thread vient de rafraîchir (< _COALESCE_WINDOW),
      on renvoie le token déjà à jour au lieu de re-rafraîchir (anti-storm rotation).
    """
    with _lock:
        now_wall = time.time()
        now_mono = time.monotonic()
        if _access_token is None:
            _perform_login()
        elif force:
            if now_mono - _last_refresh >= _COALESCE_WINDOW:
                _do_refresh()
            # sinon : un refresh très récent a déjà produit un token neuf → réutilisé
        elif _access_exp - now_wall <= _REFRESH_MARGIN:
            _do_refresh()
        return _access_token


def get_auth_headers(force: bool = False) -> dict:
    """En-têtes d'auth. Passer force=True après un 401 pour garantir un token neuf."""
    return {"Authorization": f"Bearer {get_bearer_token(force=force)}"}


logger.info("Initialisation du module d'authentification...")
with _lock:
    _perform_login()
logger.info("Module d'authentification prêt")

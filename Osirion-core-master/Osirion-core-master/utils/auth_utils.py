# auth.py
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

_access_token: str | None = None
_refresh_token: str | None = None
# Timestamp of last successful /auth/me check — avoid calling it on every recognition
_last_token_check: float = 0.0
_TOKEN_CHECK_INTERVAL = 60.0  # re-validate at most once per minute


def _perform_login():
    global _access_token, _refresh_token, _last_token_check
    logger.info("Connexion à l'API en cours...")
    resp = requests.post(
        f"{API_URL}/auth/login",
        json={"email": EMAIL, "password": PASSWORD},
        timeout=15
    )
    if resp.status_code != 200:
        raise ConnectionError(f"Login échoué ({resp.status_code}) : {resp.text}")

    data = resp.json()
    _access_token = data.get("access_token") or data.get("token")
    _refresh_token = data.get("refresh_token") or data.get("refreshToken")

    if not _access_token:
        raise ValueError("access_token non reçu lors du login")

    _last_token_check = time.monotonic()
    logger.info("Connexion réussie à l'API")


def _refresh_if_needed():
    global _access_token, _refresh_token, _last_token_check

    if not _refresh_token:
        _perform_login()
        return

    resp = requests.post(
        f"{API_URL}/auth/refresh",
        json={"refresh_token": _refresh_token},
        timeout=10
    )
    if resp.status_code == 200:
        data = resp.json()
        _access_token = data.get("access_token") or data.get("token")
        new_refresh = data.get("refresh_token") or data.get("refreshToken")
        if new_refresh:
            _refresh_token = new_refresh
        _last_token_check = time.monotonic()
        logger.debug("Token rafraîchi automatiquement")
    else:
        logger.warning("Refresh échoué, reconnexion complète")
        _perform_login()


def get_bearer_token() -> str:
    """Retourne un token valide. Vérifie /auth/me au plus une fois par minute."""
    global _access_token, _last_token_check

    if _access_token is None:
        _perform_login()
        return _access_token

    # Skip the /auth/me round-trip if we validated recently
    if time.monotonic() - _last_token_check < _TOKEN_CHECK_INTERVAL:
        return _access_token

    test = requests.get(
        f"{API_URL}/auth/me",
        headers={"Authorization": f"Bearer {_access_token}"},
        timeout=8
    )

    if test.status_code == 401:
        _refresh_if_needed()
    else:
        _last_token_check = time.monotonic()

    return _access_token


def get_auth_headers():
    return {"Authorization": f"Bearer {get_bearer_token()}"}


logger.info("Initialisation du module d'authentification...")
_perform_login()
logger.info("Module d'authentification prêt")
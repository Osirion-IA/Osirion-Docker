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

DISJONCTEUR PARTAGÉ (campagne d'observation d'août 2026)
--------------------------------------------------------
La passerelle HikCentral a renvoyé 44 902 fois `HTTP 502` en sept jours. Or le
Core, voyant ses caméras en difficulté, redemandait une URL avec `refresh=True`
— ce qui CONTOURNE le cache de 240 s du backend. Quinze caméras en difficulté
simultanée, une supervision toutes les 15 s : la passerelle déjà saturée recevait
un flot de demandes forcées. Le mécanisme d'auto-guérison ALIMENTAIT la panne.

D'où ce disjoncteur, volontairement PARTAGÉ par toutes les caméras (et non par
caméra) : la panne observée est celle d'une dépendance commune, pas d'un appareil.
Au-delà de `HIK_RESOLVE_FAIL_THRESHOLD` échecs consécutifs, les résolutions sont
suspendues pendant un délai qui double à chaque échec supplémentaire, plafonné.
Le disjoncteur se réarme dès la première résolution réussie.
"""
import os
import threading
import time
from typing import Optional

from utils.api_client import request_with_auth
from utils.logger import get_logger

logger = get_logger(__name__)

# Échecs consécutifs (toutes caméras confondues) avant d'ouvrir le disjoncteur.
_FAIL_THRESHOLD = int(os.getenv("HIK_RESOLVE_FAIL_THRESHOLD", "3"))
# Délai de suspension initial, puis doublé à chaque échec, plafonné.
_BACKOFF_BASE = float(os.getenv("HIK_RESOLVE_BACKOFF_BASE", "30"))
_BACKOFF_MAX = float(os.getenv("HIK_RESOLVE_BACKOFF_MAX", "300"))

_lock = threading.Lock()
_consecutive_failures = 0
_open_until = 0.0          # monotonic ; 0 = disjoncteur fermé
_total_ok = 0
_total_fail = 0
_suppressed = 0            # appels court-circuités (jamais partis vers le backend)


def resolver_health() -> dict:
    """Instantané du disjoncteur — publié dans les métriques système.

    Permet de distinguer, depuis `metrics.jsonl` seul, une panne de la PASSERELLE
    (breaker_open=True, échecs qui grimpent) d'une panne d'une caméra isolée.
    """
    with _lock:
        remaining = max(0.0, _open_until - time.monotonic())
        return {
            "hik_resolve_ok": _total_ok,
            "hik_resolve_fail": _total_fail,
            "hik_resolve_suppressed": _suppressed,
            "hik_backoff_open": remaining > 0,
            "hik_backoff_remaining_s": round(remaining, 1),
            "hik_consecutive_failures": _consecutive_failures,
        }


def _note_success() -> None:
    """Réarme le disjoncteur : une seule réussite suffit."""
    global _consecutive_failures, _open_until, _total_ok
    with _lock:
        was_open = _open_until > time.monotonic()
        _consecutive_failures = 0
        _open_until = 0.0
        _total_ok += 1
    if was_open:
        logger.info(
            "Passerelle HikCentral de nouveau joignable — disjoncteur refermé, "
            "résolutions d'URL reprises."
        )


def _note_failure() -> None:
    """Compte l'échec et, au-delà du seuil, ouvre le disjoncteur avec backoff."""
    global _consecutive_failures, _open_until, _total_fail
    with _lock:
        _consecutive_failures += 1
        _total_fail += 1
        if _consecutive_failures < _FAIL_THRESHOLD:
            return
        # Exposant borné : évite tout débordement après de très nombreux échecs.
        exp = min(_consecutive_failures - _FAIL_THRESHOLD, 16)
        delay = min(_BACKOFF_BASE * (2 ** exp), _BACKOFF_MAX)
        _open_until = time.monotonic() + delay
        failures = _consecutive_failures
    logger.error(
        f"Passerelle HikCentral injoignable ({failures} échecs consécutifs) — "
        f"résolutions d'URL suspendues {delay:.0f}s pour ne pas aggraver la panne.",
        extra={"consecutive_failures": failures, "backoff_s": delay},
    )


def _breaker_blocks() -> bool:
    """Le disjoncteur est-il ouvert ? Incrémente le compteur de suppressions."""
    global _suppressed
    with _lock:
        if _open_until <= time.monotonic():
            return False
        _suppressed += 1
        return True


def _degraded() -> bool:
    """Des échecs récents ? Alors on NE FORCE PLUS le rafraîchissement.

    Contourner le cache backend pendant que la passerelle est en difficulté, c'est
    exactement ce qui transformait un incident en panne totale. Mieux vaut servir
    une URL de cache peut-être périmée que marteler une passerelle en 502.
    """
    with _lock:
        return _consecutive_failures > 0


def resolve_stream_url(cam_id: int, refresh: bool = False) -> Optional[str]:
    """URL RTSP standard fraîche pour une caméra HikCentral, ou None si indisponible."""
    if _breaker_blocks():
        logger.debug(
            f"Résolution URL HikCentral caméra {cam_id} court-circuitée "
            "(disjoncteur ouvert)."
        )
        return None

    # Le rafraîchissement forcé est neutralisé dès le premier échec : il ne
    # reprend qu'une fois la passerelle démontrée joignable.
    if refresh and _degraded():
        refresh = False

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
            _note_failure()
            return None
        url = resp.json().get("url")
        if not url:
            logger.warning(f"Résolution URL HikCentral caméra {cam_id} : réponse sans url.")
            _note_failure()
            return None
        _note_success()
        return url
    except Exception as e:  # noqa: BLE001 — best-effort, jamais bloquant
        logger.warning(f"Résolution URL HikCentral caméra {cam_id} échouée : {e}")
        _note_failure()
        return None

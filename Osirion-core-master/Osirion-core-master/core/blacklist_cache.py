# core/blacklist_cache.py
"""
Cache « liste de surveillance » rafraîchi depuis le backend.

Problème résolu : une fois une personne mise en cache dans le GlobalPersonTracker,
le Core ne réinterrogeait plus le backend et réutilisait indéfiniment le flag
`is_blacklisted` mémorisé (TTL 300s sans cesse rafraîchi tant que la personne est
vue). Conséquence : (dé)marquer quelqu'un comme blacklisté n'était pas pris en
compte à chaud (ni overlay rouge, ni toast/son, ni alerte).

Solution : un petit thread d'arrière-plan interroge périodiquement le backend
(GET /people/blacklist/) et maintient un frozenset d'identifiants People.id. Ce
set est consulté comme SOURCE DE VÉRITÉ par le pipeline de reconnaissance : il
prime sur le flag potentiellement périmé du cache. Symétrique : gère aussi bien
le blacklist que le déblacklist.

Tolérant aux pannes : en cas d'erreur réseau / HTTP, on CONSERVE la dernière liste
connue (on ne « débraque » jamais une personne à cause d'un hoquet réseau).
Aucune dépendance nouvelle (requests est déjà utilisé par utils.auth_utils).
"""
import threading

import requests

from utils.auth_utils import API_URL, get_auth_headers
from utils.logger import get_logger

logger = get_logger(__name__)

_DEFAULT_REFRESH_SECONDS = 5.0
_REQUEST_TIMEOUT = 5  # secondes


class BlacklistCache:
    """Set d'identifiants People.id blacklistés, rafraîchi en arrière-plan."""

    def __init__(self, refresh_seconds: float = _DEFAULT_REFRESH_SECONDS):
        self._ids: frozenset = frozenset()
        self._loaded = False          # True dès le 1er refresh réussi
        self._refresh_seconds = refresh_seconds
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None

    # ── cycle de vie ────────────────────────────────────────────────────────
    def start(self) -> None:
        """Démarre le thread de rafraîchissement (idempotent)."""
        if self._thread is not None:
            return
        # Premier chargement synchrone et best-effort : si le backend répond, le
        # set est prêt dès la 1re reconnaissance ; sinon le poll réessaiera.
        self.refresh_once()
        self._thread = threading.Thread(
            target=self._loop, name="blacklist-refresh", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        while not self._stop.is_set():
            self._stop.wait(self._refresh_seconds)
            if self._stop.is_set():
                break
            self.refresh_once()

    # ── rafraîchissement ─────────────────────────────────────────────────────
    def refresh_once(self) -> None:
        """Interroge le backend ; conserve la liste précédente en cas d'échec."""
        try:
            resp = requests.get(
                f"{API_URL}/people/blacklist/",
                headers=get_auth_headers(),
                timeout=_REQUEST_TIMEOUT,
            )
        except Exception as e:  # réseau / DNS / timeout
            logger.warning(
                f"[blacklist] refresh impossible ({e}) — conservation de la liste précédente"
            )
            return

        if resp.status_code != 200:
            logger.warning(
                f"[blacklist] refresh HTTP {resp.status_code} — conservation de la liste précédente"
            )
            return

        try:
            data = resp.json()
            new_ids = frozenset(int(x) for x in data.get("ids", []))
        except Exception as e:
            logger.warning(f"[blacklist] réponse illisible ({e}) — liste précédente conservée")
            return

        with self._lock:
            changed = (not self._loaded) or (new_ids != self._ids)
            self._ids = new_ids
            self._loaded = True

        if changed:
            logger.info(
                f"[blacklist] liste de surveillance rafraîchie : "
                f"{sorted(new_ids)} ({len(new_ids)} personne(s))"
            )

    # ── consultation ─────────────────────────────────────────────────────────
    def is_blacklisted(self, person_db_id):
        """True / False si on peut trancher, None si indéterminé (→ fallback appelant).

        Renvoie None quand l'id backend est inconnu (None) ou que la liste n'a pas
        encore été chargée : l'appelant garde alors son flag précédent (aucune
        régression). Sinon, l'appartenance au set fait foi (gère blacklist ET
        déblacklist)."""
        if person_db_id is None:
            return None
        with self._lock:
            if not self._loaded:
                return None
            return int(person_db_id) in self._ids


# ── Singleton partagé entre toutes les caméras ───────────────────────────────
_singleton = None
_singleton_lock = threading.Lock()


def get_blacklist_cache() -> BlacklistCache:
    """Retourne le cache partagé, en démarrant son thread au 1er appel."""
    global _singleton
    if _singleton is None:
        with _singleton_lock:
            if _singleton is None:
                inst = BlacklistCache()
                inst.start()
                _singleton = inst
    return _singleton

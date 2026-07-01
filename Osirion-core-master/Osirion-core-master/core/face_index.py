# core/face_index.py
"""
Réplique LOCALE (lecture seule) de la galerie de visages — index FAISS dans le Core.

Objectif : faire la recherche d'embeddings SANS round-trip HTTP vers le backend.
PostgreSQL reste l'unique propriété du backend ; le Core garde en RAM une copie des
embeddings + métadonnées (nom, statut blacklist), rafraîchie :
  1. au démarrage (chargement initial via GET /people/embeddings/),
  2. périodiquement (poll de version via GET /people/embeddings/version),
     ce qui rattrape tout enrôlement / changement de blacklist.

SÛRETÉ — ce module ne casse jamais le pipeline :
  - activé uniquement si FAISS_LOCAL=true (sinon il n'est même pas importé) ;
  - search() renvoie None si l'index n'est pas prêt ou en cas d'erreur → l'appelant
    (embeddings_search_service.search_embedding_async) retombe sur le chemin HTTP.

Le format de sortie de search() est IDENTIQUE à
backend app/services/Faiss_search_service.py::search_similar_people, afin que le
reste du Core (TrackingProcessor._decide_one) soit inchangé.
"""
import threading

import numpy as np
import requests

from utils.auth_utils import API_URL, get_auth_headers
from utils.logger import get_logger

logger = get_logger(__name__)

_DIM = 512

# Sur-échantillonnage pour le max-cosine par personne (galerie multi-vecteurs :
# plusieurs lignes partagent le même `id` de personne). Identique au backend.
_POOL_OVERFETCH_FACTOR = 10
_POOL_OVERFETCH_MIN = 50

# État global protégé par _lock (réentrant : _build appelé sous chargement).
_lock = threading.RLock()
_index = None          # faiss.IndexFlatIP | None
_meta: list = []       # métadonnées alignées sur l'ordre d'ajout FAISS
_version = None        # version de galerie chargée (str) | None
_ready = False         # True dès qu'un chargement a réussi
_stop = threading.Event()
_reconcile_thread = None

try:
    import faiss
except Exception as exc:  # pragma: no cover - dépend de l'image
    faiss = None
    logger.error(f"[face_index] FAISS indisponible — recherche locale désactivée : {exc}")


# ──────────────────────────────────────────────────────────────────────────────
# Construction de l'index
# ──────────────────────────────────────────────────────────────────────────────
def _build(people: list) -> None:
    """(Re)construit l'index à partir de la galerie reçue du backend.

    Le travail lourd (normalisation + add FAISS) se fait HORS verrou ; seul
    l'échange atomique index/meta est verrouillé pour ne pas bloquer search()."""
    if faiss is None:
        return

    n = len(people)
    if n == 0:
        with _lock:
            global _index, _meta
            _index = None
            _meta = []
        logger.info("[face_index] galerie vide — index local réinitialisé.")
        return

    xb = np.asarray([p["embedding"] for p in people], dtype="float32")
    faiss.normalize_L2(xb)  # IndexFlatIP = cosine exact sur vecteurs normalisés
    new_index = faiss.IndexFlatIP(_DIM)
    new_index.add(xb)

    new_meta = [
        {
            "id": p.get("id"),
            "name": p.get("name", "Inconnu"),
            "is_blacklisted": bool(p.get("is_blacklisted", False)),
            "blacklist_reason": p.get("blacklist_reason"),
            "phone": p.get("phone"),
            "email": p.get("email"),
            "image_url": p.get("image_url"),
        }
        for p in people
    ]

    with _lock:
        _index = new_index
        _meta = new_meta


# ──────────────────────────────────────────────────────────────────────────────
# Synchronisation avec le backend
# ──────────────────────────────────────────────────────────────────────────────
def _fetch_version(timeout: int = 8):
    resp = requests.get(
        f"{API_URL}/people/embeddings/version",
        headers=get_auth_headers(),
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json().get("version")


def load_from_backend(timeout: int = 30) -> bool:
    """Charge la galerie complète et (re)construit l'index. Retourne True si OK."""
    global _version, _ready
    if faiss is None:
        return False

    resp = requests.get(
        f"{API_URL}/people/embeddings/",
        headers=get_auth_headers(),
        timeout=timeout,
    )
    resp.raise_for_status()
    data = resp.json()
    people = data.get("people", [])
    _build(people)
    _version = data.get("version")
    _ready = True
    logger.info(
        f"[face_index] index local prêt : {len(people)} visage(s) "
        f"(version={_version})."
    )
    return True


def _reconcile_loop(interval: float) -> None:
    """Poll périodique : si la version de galerie a changé, on recharge.
    Rattrape aussi un chargement initial qui aurait échoué."""
    while not _stop.wait(interval):
        try:
            remote = _fetch_version()
            if remote is not None and remote != _version:
                logger.info(
                    f"[face_index] version galerie modifiée "
                    f"({_version} → {remote}) — rechargement de la copie locale."
                )
                load_from_backend()
        except Exception as exc:
            logger.warning(f"[face_index] réconciliation échouée (réessai) : {exc}")


# ──────────────────────────────────────────────────────────────────────────────
# API publique
# ──────────────────────────────────────────────────────────────────────────────
def is_ready() -> bool:
    return _ready and _index is not None and faiss is not None


def search(embedding, k: int = 1):
    """Recherche locale max-cosine PAR PERSONNE. Retourne une liste (éventuellement
    vide) au MÊME format que le backend, ou None pour signaler « index indisponible
    → repli HTTP ».

    Multi-vecteurs : plusieurs entrées FAISS partagent le même `id` de personne. On
    sur-échantillonne les voisins puis on regroupe par `id` en gardant le score MAX,
    et on renvoie les `k` meilleures personnes (jamais de doublon de personne)."""
    if not is_ready() or embedding is None:
        return None
    try:
        query = np.asarray([embedding], dtype="float32")
        faiss.normalize_L2(query)
        with _lock:
            if _index is None or _index.ntotal == 0:
                return []
            fetch_k = min(
                max(k * _POOL_OVERFETCH_FACTOR, _POOL_OVERFETCH_MIN),
                _index.ntotal,
            )
            distances, indices = _index.search(query, fetch_k)
            # Pooling : id de personne → (meilleur score, meta de cette pose).
            best: dict = {}
            for cosine_sim, idx in zip(distances[0], indices[0]):
                if idx == -1:
                    continue
                meta = _meta[idx]
                pid = meta.get("id")
                score = max(0.0, float(cosine_sim))
                if pid not in best or score > best[pid][0]:
                    best[pid] = (score, meta)

        top = sorted(best.values(), key=lambda sm: sm[0], reverse=True)[:k]
        results = []
        for score, meta in top:
            s = round(score, 4)
            results.append({
                **meta,
                "cosine_similarity": s,  # cohérent avec le backend
                "score": s,
            })
        return results
    except Exception as exc:
        # Toute erreur locale → None pour forcer le repli HTTP (jamais de crash).
        logger.warning(f"[face_index] recherche locale en échec — repli HTTP : {exc}")
        return None


def init(reconcile_interval: float = 15) -> bool:
    """Chargement initial + démarrage du thread de réconciliation.
    Non bloquant pour le pipeline : un échec laisse _ready=False (repli HTTP),
    et la réconciliation réessaiera automatiquement."""
    global _reconcile_thread
    if faiss is None:
        logger.error("[face_index] FAISS absent — recherche locale impossible (repli HTTP).")
        return False

    try:
        load_from_backend()
    except Exception as exc:
        logger.error(f"[face_index] chargement initial KO (repli HTTP, réessai auto) : {exc}")

    if _reconcile_thread is None:
        _stop.clear()
        _reconcile_thread = threading.Thread(
            target=_reconcile_loop,
            args=(reconcile_interval,),
            name="face-index-reconcile",
            daemon=True,
        )
        _reconcile_thread.start()
    return is_ready()


def stop() -> None:
    _stop.set()

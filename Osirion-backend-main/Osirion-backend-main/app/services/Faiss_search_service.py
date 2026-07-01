import faiss
import numpy as np
import threading
import logging
from sqlmodel import Session, select
from app.database import engine
from app.models.people import People, PersonEmbedding

logger = logging.getLogger(__name__)

d = 512
index = None
# Position FAISS → person_id (People.id). MULTI-VECTEURS : plusieurs positions
# peuvent pointer vers le MÊME person_id (un visage par angle/éclairage).
faiss_to_db_id: dict = {}
_index_lock = threading.Lock()

# Sur-échantillonnage pour le max-cosine : comme une personne possède désormais
# plusieurs vecteurs, on récupère beaucoup plus de voisins que de personnes
# voulues, puis on regroupe par person_id en gardant le MAX. Facteur large +
# plancher pour que le top-k de PERSONNES soit fiable même si une personne
# « monopolise » les premiers voisins.
_POOL_OVERFETCH_FACTOR = 10
_POOL_OVERFETCH_MIN = 50

# Métrique : Inner Product sur vecteurs L2-normalisés = similarité cosinus ∈ [0, 1]
# Avantage vs IndexFlatL2 : score direct sans conversion non-linéaire, range utile [0.05–0.95]
# vs ancienne formule 1/(1+L2) qui compressait tout dans [0.41–0.70]


def _normalize(xb: np.ndarray) -> np.ndarray:
    """Normalise les vecteurs L2 en place et retourne le tableau normalisé."""
    faiss.normalize_L2(xb)
    return xb


def build_or_reload_faiss_index() -> None:
    global index, faiss_to_db_id

    with _index_lock:
        with Session(engine) as session:
            # MULTI-VECTEURS : on charge toutes les lignes person_embeddings ;
            # `ids` contient le person_id (répété) aligné sur chaque vecteur.
            rows = session.exec(
                select(PersonEmbedding.person_id, PersonEmbedding.embedding)
                .where(PersonEmbedding.embedding.is_not(None))
            ).all()

        if not rows:
            logger.info("Aucun embedding en base — index FAISS non construit.")
            return

        ids, embeddings = zip(*rows)
        xb = np.array(embeddings, dtype='float32')
        n_vectors = len(xb)

        # Log des normes AVANT normalisation pour détecter le drift pgvector (round-trip float32)
        # Si norme min < 0.999 ou max > 1.001 → dérive détectée, normalisation critique
        norms_raw = np.linalg.norm(xb, axis=1)
        logger.info(
            f"Embeddings chargés (brut pgvector) : n={n_vectors}, "
            f"norme min={norms_raw.min():.6f}, max={norms_raw.max():.6f}, μ={norms_raw.mean():.6f}"
        )
        if norms_raw.min() < 0.999 or norms_raw.max() > 1.001:
            logger.warning(
                f"Drift de norme détecté après round-trip pgvector "
                f"(min={norms_raw.min():.6f}, max={norms_raw.max():.6f}) — "
                "re-normalisation appliquée."
            )

        # Métrique structurée pour monitoring (ingérée par ELK/Loki/Grafana)
        try:
            import json, time as _time
            _monitor = logging.getLogger("osirion.monitoring")
            _monitor.info(json.dumps({
                "ts": _time.time(), "event": "norm_drift",
                "norm_min": round(float(norms_raw.min()), 6),
                "norm_max": round(float(norms_raw.max()), 6),
                "norm_mean": round(float(norms_raw.mean()), 6),
                "norm_drift": round(float(norms_raw.max() - norms_raw.min()), 6),
                "n_vectors": n_vectors,
                "drift_detected": bool(norms_raw.min() < 0.999 or norms_raw.max() > 1.001),
            }))
        except Exception:
            pass  # monitoring non-bloquant

        _normalize(xb)  # garantit norme=1.0 pour IndexFlatIP (cosine exact)

        if n_vectors < 1000:
            new_index = faiss.IndexFlatIP(d)  # cosine similarity directe pour vecteurs normalisés
            new_index.add(xb)
            logger.info(f"FAISS IndexFlatIP construit : {n_vectors} vecteurs.")
        elif n_vectors < 1_000_000:
            nlist = min(16384, n_vectors)
            quantizer = faiss.IndexFlatIP(d)
            new_index = faiss.IndexIVFFlat(quantizer, d, nlist, faiss.METRIC_INNER_PRODUCT)
            logger.info(f"Construction FAISS IndexIVFFlat (IP) — {n_vectors:,} vecteurs...")
            new_index.train(xb)
            new_index.add_with_ids(xb, np.arange(n_vectors, dtype='int64'))
        else:
            nlist = 32768
            quantizer = faiss.IndexFlatIP(d)
            new_index = faiss.IndexIVFPQ(quantizer, d, nlist, 64, 8)
            new_index.metric_type = faiss.METRIC_INNER_PRODUCT
            logger.info(f"Construction FAISS IndexIVFPQ (IP) — {n_vectors:,} vecteurs...")
            new_index.train(xb)
            new_index.add_with_ids(xb, np.arange(n_vectors, dtype='int64'))

        index = new_index
        faiss_to_db_id = {i: pid for i, pid in enumerate(ids)}
        logger.info(f"FAISS prêt : {index.ntotal} vecteurs indexés (métrique=IP).")


def add_person_to_index(person_id: int, embedding: list) -> None:
    """Ajoute un vecteur normalisé à l'index existant sans reconstruire entièrement."""
    global index, faiss_to_db_id

    with _index_lock:
        if index is None:
            build_or_reload_faiss_index()
            return

        vec = np.array([embedding], dtype='float32')
        _normalize(vec)  # normalisation défensive avant ajout
        new_faiss_id = len(faiss_to_db_id)

        if isinstance(index, faiss.IndexFlatIP):
            index.add(vec)
        else:
            index.add_with_ids(vec, np.array([new_faiss_id], dtype='int64'))

        faiss_to_db_id[new_faiss_id] = person_id
        logger.info(f"FAISS : personne id={person_id} ajoutée (total={index.ntotal})")


def search_similar_people(embedding: list, k: int = 1) -> list:
    """Recherche max-cosine PAR PERSONNE.

    Multi-vecteurs : une personne a plusieurs vecteurs dans l'index. On sur-échantillonne
    les voisins FAISS, on regroupe par person_id en gardant le score MAXIMUM (la pose
    la plus ressemblante décide), puis on renvoie les `k` MEILLEURES personnes —
    jamais la même personne deux fois. Le format de sortie est inchangé."""
    global index, faiss_to_db_id

    if index is None or index.ntotal == 0:
        return []

    query = np.array([embedding], dtype='float32')
    _normalize(query)  # normalisation obligatoire — IndexFlatIP retourne cosine seulement si norme=1

    # On récupère bien plus de voisins que de personnes voulues : plusieurs des
    # premiers voisins peuvent appartenir à la même personne.
    fetch_k = min(max(k * _POOL_OVERFETCH_FACTOR, _POOL_OVERFETCH_MIN), index.ntotal)

    if hasattr(index, 'nprobe'):
        # nprobe relevé : le sur-échantillonnage doit explorer assez de cellules IVF
        # pour ne pas rater la meilleure pose d'une personne.
        index.nprobe = 32

    D, I = index.search(query, fetch_k)

    # D[0] = similarités cosinus ∈ [−1, 1] (typiquement [0, 1] pour ArcFace).
    logger.debug(
        f"FAISS search : top-{fetch_k} scores bruts = "
        f"{[round(float(s), 4) for s in D[0]]}"
    )

    # ── Pooling max-cosine : person_id → meilleur score observé ──
    best_by_person: dict[int, float] = {}
    for cosine_sim, idx in zip(D[0], I[0]):
        if idx == -1:
            continue
        person_id = faiss_to_db_id.get(int(idx))
        if person_id is None:
            continue
        score = max(0.0, float(cosine_sim))  # clamp négatifs (jamais pour ArcFace normal)
        if score > best_by_person.get(person_id, -1.0):
            best_by_person[person_id] = score

    if not best_by_person:
        return []

    # Top-k PERSONNES par score décroissant.
    top_people = sorted(best_by_person.items(), key=lambda kv: kv[1], reverse=True)[:k]

    results = []
    with Session(engine) as session:
        for person_id, score in top_people:
            person = session.get(People, person_id)
            if not person:
                continue
            score = round(score, 4)
            results.append({
                "id": person.id,
                "name": f"{person.first_name} {person.last_name}",
                "phone": person.phone,
                "email": person.email,
                "image_url": person.image_url,
                # Statut liste de surveillance — consommé par le Core pour
                # déclencher l'alerte (overlay rouge + toast/son).
                "is_blacklisted": bool(getattr(person, "is_blacklisted", False)),
                "blacklist_reason": getattr(person, "blacklist_reason", None),
                "cosine_similarity": score,  # renommé pour clarté sémantique
                "score": score,              # conservé pour rétrocompatibilité API
            })

    return results

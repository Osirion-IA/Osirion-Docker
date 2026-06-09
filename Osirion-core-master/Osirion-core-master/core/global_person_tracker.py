# core/global_person_tracker.py
"""
Gestionnaire global de tracking multi-caméra
Partage les identités reconnues entre toutes les caméras
"""
import threading
import time
import numpy as np
from collections import deque
from typing import Dict, Optional, List
from utils.logger import get_logger

logger = get_logger(__name__)

_TRACK_HISTORY_MAX = 100  # entrées max dans l'historique par personne


class GlobalPersonTracker:
    """
    Gestionnaire centralisé des personnes détectées sur toutes les caméras

    Fonctionnalités :
    - Cache global des personnes reconnues
    - Évite la reconnaissance répétée entre caméras
    - Tracking des déplacements inter-caméra
    - Nettoyage automatique des entrées expirées
    """

    def __init__(self, cache_ttl_seconds: int = 300, similarity_threshold: float = 0.50):
        # Seuil 0.50 : cosine direct IndexFlatIP — ancienne valeur 0.75 était sur échelle (cosine+1)/2
        self.cache_ttl_seconds = cache_ttl_seconds
        self.similarity_threshold = similarity_threshold

        self.global_persons: Dict[int, Dict] = {}
        self.lock = threading.Lock()
        self.next_person_id = 1

        self.stats = {
            "total_recognitions": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "total_persons_tracked": 0
        }

        logger.info(
            f"GlobalPersonTracker initialisé (TTL={cache_ttl_seconds}s, seuil={similarity_threshold})"
        )

    def find_person_by_embedding(self, embedding: np.ndarray, camera_id: int) -> Optional[Dict]:
        """
        Cherche une personne dans le cache global via son embedding.

        Fix #3 : snapshot rapide sous lock, calcul cosinus effectué HORS lock.
        Avant : le lock était tenu pendant toute la boucle de comparaison →
                toutes les autres caméras bloquaient pendant les dot products CPU.
        """
        # Étape 1 : snapshot des embeddings actifs (rapide, sous lock)
        with self.lock:
            current_time = time.time()
            snapshot = [
                (pid,
                 data["embedding"].copy(),
                 data["name"],
                 data["last_seen_camera"],
                 data["last_seen_time"],
                 data.get("is_blacklisted", False))
                for pid, data in self.global_persons.items()
                if current_time - data["last_seen_time"] <= self.cache_ttl_seconds
            ]

        # Étape 2 : similarité cosinus vectorisée (numpy batch)
        # Fix perf #3 : avant → boucle Python O(n) avec un dot product par personne
        #               après → une seule opération matricielle (N, 512) @ (512,) → O(1) numpy
        # Fix métrique : suppression du scaling (sim+1)/2 — les embeddings ArcFace ont cosine ∈ [0,1]
        #                les deux systèmes (FAISS + GlobalTracker) utilisent maintenant la même échelle
        best_match = None
        if snapshot:
            pids, cached_embs, names, cameras, times, blacklists = zip(*snapshot)
            matrix = np.stack(cached_embs)                    # (N, 512)
            query_norm = np.linalg.norm(embedding)
            matrix_norms = np.linalg.norm(matrix, axis=1)    # (N,)

            similarities = np.zeros(len(pids))
            if query_norm > 0:
                valid = matrix_norms > 0
                similarities[valid] = (
                    matrix[valid] @ embedding
                ) / (matrix_norms[valid] * query_norm)
            similarities = np.maximum(similarities, 0.0)     # clamp négatifs — cosine ArcFace est ≥ 0 en pratique

            best_idx = int(np.argmax(similarities))
            best_score = float(similarities[best_idx])
            if best_score >= self.similarity_threshold:
                current_time = time.time()
                best_match = {
                    "person_id": pids[best_idx],
                    "name": names[best_idx],
                    "score": best_score,
                    "is_blacklisted": bool(blacklists[best_idx]),
                    "previous_camera": cameras[best_idx],
                    "time_since_last_seen": current_time - times[best_idx]
                }

        # Étape 3 : mise à jour des stats (sous lock)
        with self.lock:
            if best_match:
                self.stats["cache_hits"] += 1
                logger.debug(
                    f"Cache HIT : {best_match['name']} (score={best_score:.3f})",
                    extra={
                        'person_id': best_match['person_id'],
                        'camera_id': camera_id,
                        'previous_camera': best_match['previous_camera'],
                        'similarity_score': best_score
                    }
                )
            else:
                self.stats["cache_misses"] += 1

        return best_match

    def find_or_register(
        self,
        name: str,
        embedding: np.ndarray,
        camera_id: int,
        track_id: int,
        recognition_score: float,
        is_blacklisted: bool = False
    ) -> int:
        """
        Fix #1 : find-then-register ATOMIQUE sous un seul verrou.

        Sans cette méthode, deux caméras qui reconnaissent la même personne
        simultanément passaient toutes deux find_person_by_embedding → None,
        puis appelaient register_person → doublon dans le cache.

        Ici, la vérification finale et l'enregistrement sont dans le même bloc
        with self.lock, ce qui rend l'opération indivisible.
        """
        with self.lock:
            current_time = time.time()

            # Vérification finale vectorisée sous lock (remplace la boucle O(N) per-person).
            # Même logique que find_person_by_embedding mais atomique (sous lock).
            active_items = [
                (pid, data) for pid, data in self.global_persons.items()
                if current_time - data["last_seen_time"] <= self.cache_ttl_seconds
            ]
            if active_items:
                pids_local, datas_local = zip(*active_items)
                matrix_local = np.stack([d["embedding"] for d in datas_local])  # (N, 512)
                query_norm = np.linalg.norm(embedding)
                matrix_norms = np.linalg.norm(matrix_local, axis=1)
                sims = np.zeros(len(pids_local))
                if query_norm > 0:
                    valid = matrix_norms > 0
                    sims[valid] = (matrix_local[valid] @ embedding) / (matrix_norms[valid] * query_norm)
                sims = np.maximum(sims, 0.0)
                best_local_idx = int(np.argmax(sims))
                if sims[best_local_idx] >= self.similarity_threshold:
                    data = datas_local[best_local_idx]
                    pid = pids_local[best_local_idx]
                    data["last_seen_time"] = current_time
                    data["last_seen_camera"] = camera_id
                    data["appearance_count"] += 1
                    data["track_history"].append((camera_id, track_id))
                    data["is_blacklisted"] = bool(is_blacklisted)   # rafraîchit le statut
                    return pid

            # Pas trouvé → enregistrement
            person_id = self.next_person_id
            self.next_person_id += 1

            self.global_persons[person_id] = {
                "name": name,
                "embedding": embedding.copy(),
                "is_blacklisted": bool(is_blacklisted),
                "first_seen_time": current_time,
                "last_seen_time": current_time,
                "first_seen_camera": camera_id,
                "last_seen_camera": camera_id,
                "cameras_visited": {camera_id},           # Fix #4 : set (O(1)) au lieu de list (O(n))
                "recognition_score": recognition_score,
                "appearance_count": 1,
                "track_history": deque(                   # Fix #2 : deque bornée, jamais de fuite mémoire
                    [(camera_id, track_id)],
                    maxlen=_TRACK_HISTORY_MAX
                ),
            }

            self.stats["total_persons_tracked"] += 1
            self.stats["total_recognitions"] += 1

            logger.info(
                f"Nouvelle personne enregistrée : {name} (person_id={person_id})",
                extra={
                    'person_id': person_id,
                    'camera_id': camera_id,
                    'track_id': track_id,
                    'recognition_score': recognition_score
                }
            )
            return person_id

    def update_person_location(self, person_id: int, camera_id: int, track_id: int) -> bool:
        """Met à jour la localisation d'une personne connue"""
        with self.lock:
            if person_id not in self.global_persons:
                return False

            data = self.global_persons[person_id]
            previous_camera = data["last_seen_camera"]

            data["last_seen_time"] = time.time()
            data["last_seen_camera"] = camera_id
            data["appearance_count"] += 1
            data["track_history"].append((camera_id, track_id))  # deque auto-cap à _TRACK_HISTORY_MAX

            if camera_id not in data["cameras_visited"]:  # Fix #4 : O(1) avec set
                data["cameras_visited"].add(camera_id)
                logger.info(
                    f"{data['name']} détecté(e) sur nouvelle caméra",
                    extra={
                        'person_id': person_id,
                        'person_name': data['name'],
                        'from_camera': previous_camera,
                        'to_camera': camera_id,
                        'total_cameras_visited': len(data['cameras_visited'])
                    }
                )
            return True

    def cleanup_expired_entries(self) -> int:
        """Supprime les entrées expirées du cache"""
        with self.lock:
            current_time = time.time()
            expired = [
                pid for pid, data in self.global_persons.items()
                if current_time - data["last_seen_time"] > self.cache_ttl_seconds
            ]
            for pid in expired:
                name = self.global_persons[pid]["name"]
                del self.global_persons[pid]
                logger.debug(f"Entrée expirée supprimée : {name}", extra={'person_id': pid})
            return len(expired)

    def get_person_info(self, person_id: int) -> Optional[Dict]:
        """Récupère les informations d'une personne par son ID global"""
        with self.lock:
            return self.global_persons.get(person_id)

    def get_all_active_persons(self) -> List[Dict]:
        """Retourne la liste de toutes les personnes actives"""
        with self.lock:
            current_time = time.time()
            return [
                {
                    "person_id": pid,
                    "name": data["name"],
                    "last_seen_camera": data["last_seen_camera"],
                    "cameras_visited": list(data["cameras_visited"]),  # set → list pour sérialisation JSON
                    "time_since_last_seen": current_time - data["last_seen_time"]
                }
                for pid, data in self.global_persons.items()
                if current_time - data["last_seen_time"] <= self.cache_ttl_seconds
            ]

    def get_statistics(self) -> Dict:
        """Retourne les statistiques d'utilisation du tracker"""
        with self.lock:
            active_count = sum(
                1 for p in self.global_persons.values()
                if time.time() - p["last_seen_time"] <= self.cache_ttl_seconds
            )

            # Fix #5 : dénominateur correct = total des recherches (hits + misses)
            # Avant : on divisait par total_recognitions (enregistrements) → taux biaisé
            total_searches = self.stats["cache_hits"] + self.stats["cache_misses"]
            cache_hit_rate = (
                self.stats["cache_hits"] / total_searches * 100
                if total_searches > 0 else 0
            )

            return {
                "active_persons": active_count,
                "total_persons_tracked": self.stats["total_persons_tracked"],
                "cache_hits": self.stats["cache_hits"],
                "cache_misses": self.stats["cache_misses"],
                "cache_hit_rate": f"{cache_hit_rate:.1f}%",
                "total_recognitions": self.stats["total_recognitions"]
            }

    @staticmethod
    def _compute_cosine_similarity(embedding1: np.ndarray, embedding2: np.ndarray) -> float:
        """
        Similarité cosinus brute ∈ [0.0, 1.0] pour embeddings ArcFace L2-normalisés.
        Suppression du scaling (sim+1)/2 — unified avec FAISS IndexFlatIP score.
        """
        norm1 = np.linalg.norm(embedding1)
        norm2 = np.linalg.norm(embedding2)
        if norm1 == 0 or norm2 == 0:
            return 0.0
        similarity = np.dot(embedding1, embedding2) / (norm1 * norm2)
        return max(0.0, float(similarity))  # clamp — jamais négatif pour faces réelles

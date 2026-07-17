# core/tracking_processor.py
"""
Traitement de la détection, du tracking et de la reconnaissance faciale
"""
import cv2
import numpy as np
import asyncio
import aiohttp
import time
from collections import deque, defaultdict
from typing import Dict, List, Optional, Tuple
import queue
import threading

from face_detection import detect_faces_with_embeddings
from services.embeddings_search_service import search_embedding_async
from services.event_services import send_event_async
from config.settings import EVENTS
from core.adaptive_threshold import AdaptiveThreshold
from core.blacklist_cache import get_blacklist_cache
from utils.logger import get_logger
from utils.monitoring import emit_recognition_metric, emit_blur_metric
from utils.measurement import get_measurement

logger = get_logger(__name__)

# Type d'événement émis pour un visage détecté mais NON reconnu (opt-in).
# Doit rester aligné sur backend app/models/events.py::EVENT_UNKNOWN_FACE.
EVENT_UNKNOWN_FACE = "UNKNOWN_FACE"

# Pondérations du score de qualité du visage (frontalité, taille, netteté). Somme
# arbitraire — re-normalisée à l'usage selon les facteurs réellement disponibles
# (la netteté n'entre que si elle a pu être mesurée). La frontalité prime car
# c'est le facteur le plus discriminant pour la fiabilité d'un embedding ArcFace.
_Q_W_FRONTALITY = 0.45
_Q_W_SIZE = 0.35
_Q_W_SHARPNESS = 0.20


class TrackingProcessor:
    """Gère le traitement de détection, tracking et reconnaissance pour une caméra"""

    def __init__(self, cam: Dict, frame_queue: queue.Queue, result_frames: Dict,
                 result_lock, tracker, person_db: Dict, frame_idx_container: Dict,
                 stop_event, config, global_tracker=None, runtime_control=None,
                 result_metadata: Dict = None):
        self.cam_id = cam["id"]
        self.cam_name = cam["cam_name"]
        self.location = cam["location"]
        self.frame_queue = frame_queue
        self.result_frames = result_frames
        # Phase 2 : on ne dessine plus sur la frame. On publie des bounding boxes
        # JSON dans result_metadata[cam_id] ; le serveur web les diffuse en
        # 'metadata'. La vidéo est servie par MediaMTX (WebRTC), pas par le Core.
        self.result_metadata = result_metadata if result_metadata is not None else {}
        self.result_lock = result_lock
        self.tracker = tracker
        self.person_db = person_db
        self.frame_idx_container = frame_idx_container
        self.stop_event = stop_event
        self.config = config
        self.global_tracker = global_tracker

        # Source de vérité « liste de surveillance » rafraîchie depuis le backend
        # (poll léger ~5s). Permet la prise en compte À CHAUD d'un (dé)blacklist
        # sans attendre l'expiration du cache global. Singleton partagé caméras.
        self.blacklist_cache = get_blacklist_cache()

        # Drapeaux activables au runtime (toggles frontend : facial, unknown-face).
        self.runtime_control = runtime_control

        # ── Config EFFECTIVE des modules PAR CAMÉRA (VMS — groupes) ───────────
        # Calculée côté backend (drapeau local ∧ tous les groupes de la caméra),
        # transmise dans le payload caméra. La boucle de supervision la met à jour
        # À CHAUD via apply_effective_config() SANS redémarrer ce thread. Défaut
        # True → aucune régression si le backend ne renvoie pas encore ces champs.
        # Lecture/écriture d'un bool = atomique sous le GIL (pas de verrou requis).
        self._effective_facial_active = bool(cam.get("effective_facial_active", True))

        self.frame_counter = 0
        self.loop = None
        self._session = None
        self._blur_skip_count = 0  # compteur de frames rejetées pour flou (monitoring)

        # ── Mesure (chapitre 4) : latence d'inférence par frame TRAITÉE ──────
        # Accumulateurs vidés à chaque échantillon par le sampler (fenêtre non
        # chevauchante). face_ms = SCRFD+alignement+ArcFace (1 passe GPU).
        self.measure = get_measurement()
        self._lat_lock = threading.Lock()
        self._face_ms: deque = deque(maxlen=4000)
        self._frame_ms: deque = deque(maxlen=4000)   # coût TOTAL par frame traitée

        # ── Worker réseau découplé pour la reconnaissance faciale ────────────
        # Le thread caméra ne bloque JAMAIS sur le réseau : il pousse un job
        # (embeddings + snapshot) dans _recognition_jobs et continue immédiatement.
        # Un thread dédié (_recognition_loop) fait la recherche FAISS + l'envoi
        # d'événement, puis renvoie les résultats via _recognition_results. Le
        # thread caméra applique ces résultats à person_db (toutes les écritures
        # de person_db restent sur le thread caméra → pas de verrou nécessaire).
        # Patron worker découplé (file de jobs + thread dédié).
        maxq = getattr(config, 'RECOGNITION_QUEUE_MAXSIZE', 64)
        self._recognition_jobs: "queue.Queue" = queue.Queue(maxsize=maxq)
        self._recognition_results: "queue.Queue" = queue.Queue()
        self._recognition_inflight: set = set()   # track_ids en cours de résolution
        self._recognition_worker: Optional[threading.Thread] = None

        # Seuil adaptatif par caméra — s'auto-calibre sur les scores observés
        # Fallbacks alignés sur l'échelle cosine IndexFlatIP (0.45/0.35/0.80)
        self.adaptive_threshold = AdaptiveThreshold(
            initial=getattr(config, 'RECOGNITION_THRESHOLD', 0.45),
            floor=getattr(config, 'ADAPTIVE_THRESHOLD_FLOOR', 0.35),
            ceiling=getattr(config, 'ADAPTIVE_THRESHOLD_CEILING', 0.80),
        )
        logger.info(
            f"[cam={self.cam_name}] AdaptiveThreshold initialisé "
            f"(départ={self.adaptive_threshold.value:.2f}, "
            f"plancher={self.adaptive_threshold.floor:.2f}, "
            f"plafond={self.adaptive_threshold.ceiling:.2f})"
        )

        # ── Précision : garde-fou de taille + vote temporel multi-frames ──────
        # Garde-fou taille : visage plus petit que ce seuil (px, plus petit côté)
        # → reconnaissance NON tentée (embedding ArcFace dégradé). 0 = désactivé.
        self.face_min_size = max(0, getattr(config, 'FACE_MIN_RECOG_SIZE', 0))
        self._face_gated_count = 0

        # Gates de QUALITÉ supplémentaires avant reconnaissance (0 = désactivé) :
        #   · frontalité : ignore les profils extrêmes (embedding ArcFace dégradé) ;
        #   · netteté du crop : ignore les visages flous même si la frame est nette
        #     (complète le BLUR_THRESHOLD qui, lui, porte sur la frame entière).
        # Un visage gaté reste affiché « Inconnu » (la box est produite) et le vote
        # temporel le rattrape dès qu'une frame de meilleure qualité arrive.
        self.face_min_frontality = max(0.0, float(getattr(config, 'FACE_MIN_FRONTALITY', 0.0)))
        self.face_crop_min_sharpness = max(0.0, float(getattr(config, 'FACE_CROP_MIN_SHARPNESS', 0.0)))
        self._face_profile_gated = 0
        self._face_blur_gated = 0

        # Best-shot : pondération du vote temporel par la qualité du visage. Quand
        # actif, on calcule un score qualité ∈ [0,1] par observation et le vote
        # privilégie les bonnes frames (cf. _face_quality / _face_vote).
        self.face_quality_weighting = bool(getattr(config, 'FACE_QUALITY_WEIGHTED_VOTE', True))
        self.face_quality_ref_size = max(1, int(getattr(config, 'FACE_QUALITY_REF_SIZE', 110)))
        self.face_quality_ref_sharpness = max(0.0, float(getattr(config, 'FACE_QUALITY_REF_SHARPNESS', 120.0)))

        # Vote temporel facial : on n'assigne un nom qu'après consensus multi-frames
        # (cf. config.settings). État de vote par track_id, possédé EXCLUSIVEMENT par
        # le thread worker (_recognition_loop traite les jobs en série → pas de verrou
        # nécessaire, même garantie que le worker OCR de PlateProcessor).
        self.face_voting = getattr(config, 'FACE_TEMPORAL_VOTING', True)
        self.face_vote_min_agree = max(1, getattr(config, 'FACE_VOTE_MIN_AGREE', 2))
        self.face_vote_max_attempts = max(1, getattr(config, 'FACE_VOTE_MAX_ATTEMPTS', 5))
        self._vote_state: Dict[int, Dict] = {}

        # ── Fusion temporelle d'embeddings (best-of-stream) ──────────────────
        # Pour chaque track actif, on garde une file bornée (FIFO) des derniers
        # embeddings 512-D bruts. AVANT la recherche FAISS, on envoie la MOYENNE
        # re-normalisée L2 de cette file plutôt qu'un embedding mono-frame : le
        # bruit par frame s'annule, la requête devient plus stable → score plus
        # haut et plus régulier. Possédé EXCLUSIVEMENT par le thread caméra
        # (alimenté dans run()), donc sans verrou. window ≤ 1 ⇒ comportement
        # mono-frame d'origine (aucune régression).
        self.face_fusion = bool(getattr(config, 'FACE_EMBEDDING_FUSION', True))
        self.face_fusion_window = max(1, int(getattr(config, 'FACE_EMBED_FUSION_WINDOW', 5)))
        self._embedding_history: Dict[int, deque] = {}
        self._embedding_last_frame: Dict[int, int] = {}

        # ── Durcissement du cache global (anti faux-positif « collant ») ──────
        # Un hit du cache global ne court-circuite le vote temporel que s'il est
        # TRÈS sûr (≥ CACHE_TRUST_THRESHOLD). En dessous, on laisse le consensus
        # multi-frames décider : un unique match mono-frame de confiance moyenne ne
        # peut plus « figer » une mauvaise identité pour toute la durée du cache.
        self.cache_trust_threshold = float(getattr(config, 'CACHE_TRUST_THRESHOLD', 0.88))

    def prepare_detections(self, faces_data: List) -> Tuple[np.ndarray, List]:
        """Prépare les détections pour le tracker (OC-SORT). Chaque entrée porte déjà son embedding GPU."""
        detections = []
        faces_indexed = []
        for (x, y, w, h), conf, embedding, frontality in faces_data:
            if embedding is None:
                continue
            x1, y1, x2, y2 = x, y, x + w, y + h
            detections.append([x1, y1, x2, y2, conf])
            faces_indexed.append((embedding, (x, y, w, h), conf, frontality))
        return np.array(detections) if detections else np.empty((0, 5)), faces_indexed

    def find_best_embedding_for_track(self, track, faces_indexed: List):
        """Retourne l'embedding le plus proche du centre du track (distance
        euclidienne 2D), avec sa frontalité — exploitée par le gate qualité.
        Renvoie (embedding, (x,y,w,h), frontalité) ; embedding=None si aucun visage."""
        tlwh = track.tlwh
        x, y, w, h = int(tlwh[0]), int(tlwh[1]), int(tlwh[2]), int(tlwh[3])
        center_x = x + w // 2
        center_y = y + h // 2

        best_embedding = None
        best_frontality = 1.0
        best_dist = float('inf')
        for embedding, bbox, _, frontality in faces_indexed:
            bx, by, bw, bh = bbox
            bc_x, bc_y = bx + bw // 2, by + bh // 2
            dist = (bc_x - center_x)**2 + (bc_y - center_y)**2
            if dist < best_dist:
                best_dist = dist
                best_embedding = embedding
                best_frontality = frontality
        return best_embedding, (x, y, w, h), best_frontality

    def _fused_embedding(self, track_id: int, embedding: np.ndarray,
                         frame_idx: int) -> np.ndarray:
        """Met à jour la file d'embeddings du track et renvoie la requête FUSIONNÉE.

        Ajoute l'embedding courant (frame valide) à la file bornée (maxlen=window)
        du track, puis renvoie la MOYENNE re-normalisée L2 des embeddings de la file.
        window ≤ 1 → renvoie l'embedding courant inchangé (mono-frame). Appelé
        uniquement sur le thread caméra → pas de verrou."""
        if not self.face_fusion or self.face_fusion_window <= 1:
            return embedding

        hist = self._embedding_history.get(track_id)
        if hist is None:
            hist = deque(maxlen=self.face_fusion_window)
            self._embedding_history[track_id] = hist
        hist.append(np.asarray(embedding, dtype=np.float32))
        self._embedding_last_frame[track_id] = frame_idx

        if len(hist) == 1:
            return hist[0]

        fused = np.mean(np.stack(hist, axis=0), axis=0)
        norm = float(np.linalg.norm(fused))
        if norm > 0:
            fused = fused / norm
        return fused.astype(np.float32)

    @staticmethod
    def _crop_sharpness(frame: np.ndarray, bbox: Tuple) -> Optional[float]:
        """Variance du Laplacien sur le CROP du visage (netteté ciblée). Retourne
        None si le crop est vide. ~0.3 ms — négligeable vs SCRFD."""
        bx, by, bw, bh = bbox
        crop = frame[max(0, by):by + bh, max(0, bx):bx + bw]
        if crop.size == 0:
            return None
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        return float(cv2.Laplacian(gray, cv2.CV_64F).var())

    def _face_quality(self, bbox: Tuple, frontality: float,
                      sharpness: Optional[float]) -> float:
        """Score de qualité du visage ∈ [0,1] (1 = visage idéal pour ArcFace).

        Moyenne pondérée de facteurs normalisés indépendants :
          · frontalité (déjà ∈ [0,1]) — poids dominant ;
          · taille     = min(plus_petit_côté / RÉF_SIZE, 1) ;
          · netteté    = min(variance_Laplacien / RÉF_SHARPNESS, 1) — incluse
                         seulement si elle a pu être mesurée.
        Sert à pondérer le vote temporel (best-shot) : les bonnes frames décident
        l'identité. Indépendant du seuil de reconnaissance (n'altère pas le cosine)."""
        front = max(0.0, min(1.0, float(frontality)))
        size_norm = min(min(bbox[2], bbox[3]) / self.face_quality_ref_size, 1.0)
        parts = [(_Q_W_FRONTALITY, front), (_Q_W_SIZE, size_norm)]
        if sharpness is not None and self.face_quality_ref_sharpness > 0.0:
            sharp_norm = min(sharpness / self.face_quality_ref_sharpness, 1.0)
            parts.append((_Q_W_SHARPNESS, sharp_norm))
        wsum = sum(w for w, _ in parts)
        if wsum <= 0.0:
            return 1.0
        return max(0.0, min(1.0, sum(w * v for w, v in parts) / wsum))

    def should_recognize_track(self, track_id: int, frame_idx: int) -> bool:
        """Détermine si un track doit être reconnu.

        Un track est (ré)interrogé si : (1) inconnu, OU (2) son identité est encore
        EN COURS DE VOTE (vote_pending → on accumule les lectures à chaque frame
        traitée jusqu'au consensus), OU (3) sa dernière reconnaissance date de plus
        de REIDENTIFICATION_INTERVAL frames."""
        entry = self.person_db.get(track_id)
        if entry is None:
            return True
        if entry.get("vote_pending"):
            return True
        return entry.get("last_updated", -1000) < frame_idx - self.config.REIDENTIFICATION_INTERVAL

    # ──────────────────────────────────────────────────────────────────────
    # Reconnaissance DÉCOUPLÉE — côté thread caméra (non bloquant)
    # ──────────────────────────────────────────────────────────────────────
    def _submit_recognition(self, items: List[Dict], frame_idx: int, frame: np.ndarray) -> None:
        """Met en file un batch de reconnaissances (recherche + événement) pour le
        worker réseau, SANS jamais bloquer le thread caméra.

        `items` : liste de dicts {track_id, x, y, w, h, embedding}.
        Les track_ids du batch sont marqués « in-flight » pour ne pas être
        re-soumis tant que le résultat n'est pas revenu (anti-spam réseau).
        """
        job = {
            "frame_idx": frame_idx,
            "frame": frame.copy(),   # snapshot figé pour l'image d'événement
            "items": items,
        }
        try:
            self._recognition_jobs.put_nowait(job)
            for it in items:
                self._recognition_inflight.add(it["track_id"])
        except queue.Full:
            logger.warning(
                f"[cam={self.cam_name}] file de reconnaissance pleine — "
                f"batch ignoré ce cycle (réessai au prochain)."
            )

    def _drain_recognition_results(self) -> None:
        """Applique (sur le thread caméra) les résultats produits par le worker.

        Toutes les écritures de person_db se font ICI → un seul thread écrivain,
        aucun verrou nécessaire (même garantie que PlateProcessor._drain_results).
        """
        while True:
            try:
                results = self._recognition_results.get_nowait()
            except queue.Empty:
                break
            for r in results:
                track_id = r["track_id"]
                self._recognition_inflight.discard(track_id)
                if r.get("failed"):
                    continue   # échec worker : on libère juste le verrou in-flight
                self.person_db[track_id] = {
                    "name": r["name"],
                    "score": r["score"],
                    "last_updated": r["frame_idx"],
                    "person_id": r["person_id"],
                    "db_id": r.get("db_id"),
                    "from_cache": r["from_cache"],
                    "is_blacklisted": r.get("is_blacklisted", False),
                    # Identité encore en cours de vote temporel → should_recognize_track
                    # ré-interroge ce track à la prochaine frame (accumulation des votes).
                    "vote_pending": r.get("vote_pending", False),
                }

    # ──────────────────────────────────────────────────────────────────────
    # Worker réseau — thread dédié (boucle asyncio + session aiohttp propres)
    # ──────────────────────────────────────────────────────────────────────
    @staticmethod
    async def _mk_session() -> aiohttp.ClientSession:
        return aiohttp.ClientSession()

    def _recognition_loop(self) -> None:
        """Boucle du worker : recherche FAISS + envoi d'événement, HORS du chemin
        critique vidéo. Possède sa propre boucle asyncio et sa session aiohttp."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        session = None
        try:
            session = loop.run_until_complete(self._mk_session())
            while not self.stop_event.is_set():
                try:
                    job = self._recognition_jobs.get(timeout=0.5)
                except queue.Empty:
                    continue
                if job is None:
                    break
                try:
                    # 1) Recherche + décision → on renvoie les résultats AU PLUS TÔT
                    #    (les noms s'affichent sans attendre l'envoi d'événement).
                    results, pending_events = loop.run_until_complete(
                        self._resolve_job(job, session)
                    )
                    self._recognition_results.put(results)
                    # 2) Événements (lents) envoyés ensuite — le thread caméra est
                    #    déjà reparti, donc cela ne ralentit jamais l'affichage.
                    if pending_events:
                        loop.run_until_complete(
                            self._send_events(pending_events, session, job["frame"])
                        )
                except Exception as e:
                    logger.error(
                        f"[cam={self.cam_name}] worker reconnaissance — job en échec : {e}",
                        exc_info=True
                    )
                    # Libérer les track_ids du job pour autoriser une nouvelle tentative.
                    self._recognition_results.put(
                        [{"track_id": it["track_id"], "failed": True} for it in job["items"]]
                    )
        except Exception as e:
            logger.error(f"[cam={self.cam_name}] worker reconnaissance arrêté : {e}", exc_info=True)
        finally:
            try:
                if session is not None:
                    loop.run_until_complete(session.close())
            except Exception:
                pass
            loop.close()

    async def _resolve_job(self, job: Dict, session: aiohttp.ClientSession) -> Tuple[List, List]:
        """Recherche FAISS en parallèle pour tout le batch, puis décision par track.

        Retourne (results, pending_events) :
          - results        : enregistrements à appliquer à person_db (thread caméra)
          - pending_events : événements à envoyer (person_id + score), traités après
        """
        items = job["items"]
        frame_idx = job["frame_idx"]

        # Purge des votes orphelins (tracks disparus avant consensus) — possédé par
        # ce seul thread worker, donc sans verrou. Borne la mémoire de _vote_state.
        if self._vote_state:
            ttl = getattr(self.config, 'CACHE_TTL_FRAMES', 600)
            stale = [tid for tid, v in self._vote_state.items()
                     if frame_idx - v.get("last_frame", frame_idx) > ttl]
            for tid in stale:
                self._vote_state.pop(tid, None)

        # Vote temporel : interroger le top-3 (pas seulement le top-1) permettrait
        # plus tard une marge top1−top2 ; ici top_k=1 suffit au vote par identité.
        search_results = await asyncio.gather(
            *[search_embedding_async(session, it["embedding"], top_k=1) for it in items]
        )

        results: List[Dict] = []
        pending_events: List[Dict] = []
        for it, search in zip(items, search_results):
            record, event = self._decide_one(it, search, frame_idx)
            results.append(record)
            if event is not None:
                pending_events.append(event)
        return results, pending_events

    def _decide_one(self, item: Dict, results: List, frame_idx: int) -> Tuple[Dict, Optional[Dict]]:
        """Décide l'identité d'un track. Orchestrateur :

          1) cache global (identités DÉJÀ confirmées → résolution immédiate),
          2) sinon, décision FAISS fraîche :
               · vote temporel multi-frames si FACE_TEMPORAL_VOTING (défaut),
               · sinon ancien comportement mono-frame (zéro régression).

        Exécuté sur le thread worker. N'écrit PAS person_db (renvoie un
        enregistrement appliqué ensuite par le thread caméra). global_tracker est
        thread-safe ; adaptive_threshold et _vote_state ne sont touchés que par ce
        worker (jobs traités en série → pas de verrou nécessaire).
        """
        # Vérité terrain attendue devant cette caméra (mode mesure ; None sinon).
        expected = self.measure.get_expected(self.cam_id)

        cached = self._decide_cached(item, frame_idx, expected)
        if cached is not None:
            return cached

        if self.face_voting:
            return self._decide_fresh_voted(item, results, frame_idx, expected)
        return self._decide_fresh_single(item, results, frame_idx, expected)

    def _decide_cached(self, item: Dict, frame_idx: int,
                       expected) -> Optional[Tuple[Dict, Optional[Dict]]]:
        """ÉTAPE 1 — résolution par le cache global. Renvoie (record, event) sur
        cache hit, None sinon (→ le caller bascule sur la décision FAISS fraîche)."""
        track_id = item["track_id"]
        embedding = item["embedding"]
        if not (self.global_tracker and embedding is not None):
            return None

        cached_match = self.global_tracker.find_person_by_embedding(embedding, self.cam_id)
        if not cached_match:
            return None

        # ── Garde-fou anti faux-positif « collant » ──────────────────────────
        # Si le score du cache est faible/moyen ET que le vote temporel est actif,
        # on NE court-circuite PAS : on renvoie None pour que la décision FAISS
        # fraîche + consensus multi-frames prenne le dessus. Seul un hit cache
        # très confiant (≥ seuil) résout immédiatement (chemin rapide inter-caméra).
        if self.face_voting and cached_match["score"] < self.cache_trust_threshold:
            logger.debug(
                f"[track_id={track_id}] cache global ignoré "
                f"(score={cached_match['score']:.3f} < {self.cache_trust_threshold:.2f}) "
                f"→ priorité au vote temporel [cam={self.cam_name}]"
            )
            return None

        name = cached_match["name"]
        # AFFICHAGE : on montre le VRAI score galerie (match FAISS mémorisé à la
        # confirmation), et NON l'auto-similarité du cache (~0.96) qui gonfle
        # artificiellement le % (le live comparé à lui-même). Repli sur l'auto-
        # similarité seulement si le score galerie est indisponible (ancien cache).
        cache_sim = cached_match["score"]
        gallery_score = cached_match.get("gallery_score")
        recognition_score = gallery_score if gallery_score is not None else cache_sim
        person_id = cached_match["person_id"]
        db_id = cached_match.get("db_id")
        is_blacklisted = bool(cached_match.get("is_blacklisted", False))
        old_blacklisted = is_blacklisted
        # Statut « surveillance » FRAIS prioritaire : un (dé)blacklist récent prime
        # sur le flag mémorisé dans le cache global (potentiellement périmé).
        bl = self.blacklist_cache.is_blacklisted(db_id)
        if bl is not None:
            is_blacklisted = bl
            if bl != old_blacklisted and person_id is not None:
                # Propage le changement (montée OU descente) dans le cache global →
                # les ré-identifications suivantes voient le bon statut sans ré-alerter.
                self.global_tracker.set_blacklist_status(person_id, bl)
        self.global_tracker.update_person_location(person_id, self.cam_id, track_id)
        logger.info(
            f"✓ Cache global : {name} — galerie={recognition_score:.0%} "
            f"(auto-sim cache={cache_sim:.2f}) [cam={self.cam_name}, track_id={track_id}]"
        )
        # Une identité confirmée par le cache clôt tout vote en cours pour ce track.
        self._vote_state.pop(track_id, None)
        # Mesure : décision servie par le cache (from_cache=True → exclue du balayage
        # EER car le score n'est pas une similarité FAISS fraîche).
        emit_recognition_metric(
            camera_id=self.cam_id,
            camera_name=self.cam_name,
            track_id=track_id,
            cosine_score=recognition_score,
            adaptive_threshold=self.adaptive_threshold.value,
            accepted=True,
            candidate_name=name,
            from_cache=True,
            expected=expected,
        )

        pending_event = None
        if is_blacklisted and not old_blacklisted:
            # TRANSITION non-surveillé → surveillé d'une personne DÉJÀ suivie : on
            # émet UNE alerte RECOGNITION sans attendre l'expiration du cache.
            pending_event = {
                "person_id": db_id if db_id is not None else (person_id if person_id is not None else -1),
                "event_type": EVENTS[0],
                "score": recognition_score,
            }
        record = {
            "track_id": track_id, "name": name, "score": recognition_score,
            "person_id": person_id, "db_id": db_id, "from_cache": True,
            "is_blacklisted": is_blacklisted, "frame_idx": frame_idx,
            "vote_pending": False,
        }
        return record, pending_event

    def _decide_fresh_single(self, item: Dict, results: List, frame_idx: int,
                             expected) -> Tuple[Dict, Optional[Dict]]:
        """ÉTAPE 2 (mono-frame) — ancien comportement : on accepte/rejette sur la
        décision FAISS d'UNE seule frame. Conservé pour FACE_TEMPORAL_VOTING=false."""
        track_id = item["track_id"]
        embedding = item["embedding"]
        name = "Inconnu"
        recognition_score = 0.0
        person_id = None
        db_id = None
        is_blacklisted = False

        if not results:
            logger.warning(
                f"[track_id={track_id}] API search : aucun résultat retourné "
                f"(index FAISS vide ou erreur réseau) [cam={self.cam_name}]"
            )
        else:
            api_score = results[0].get("score", 0)
            api_name = results[0].get("name", "?")
            current_threshold = self.adaptive_threshold.value
            self.adaptive_threshold.observe(api_score)
            accepted = api_score > current_threshold
            if api_score > 0.0 and api_score < 0.05:
                logger.warning(
                    f"[track_id={track_id}] Score anormalement bas ({api_score:.4f}) — "
                    "vérifier la normalisation L2 des embeddings (norme != 1.0 ?)"
                )
            logger.info(
                f"[track_id={track_id}] API cosine={api_score:.4f} "
                f"seuil={current_threshold:.4f} candidat={api_name!r} "
                f"→ {'ACCEPTÉ ✓' if accepted else 'REJETÉ ✗'} [cam={self.cam_name}]"
            )
            emit_recognition_metric(
                camera_id=self.cam_id,
                camera_name=self.cam_name,
                track_id=track_id,
                cosine_score=api_score,
                adaptive_threshold=current_threshold,
                accepted=accepted,
                candidate_name=api_name,
                from_cache=False,
                expected=expected,
            )

        pending_event = None
        if results and results[0].get("score", 0) > self.adaptive_threshold.value:
            name = results[0].get("name", "Inconnu")
            recognition_score = results[0].get("score", 0.0)
            db_id = results[0].get("id")
            is_blacklisted = bool(results[0].get("is_blacklisted", False))
            bl = self.blacklist_cache.is_blacklisted(db_id)
            if bl is not None:
                is_blacklisted = bl
            if self.global_tracker and embedding is not None:
                person_id = self.global_tracker.find_or_register(
                    name=name, embedding=embedding, camera_id=self.cam_id,
                    track_id=track_id, recognition_score=recognition_score,
                    is_blacklisted=is_blacklisted, db_id=db_id,
                )
            pending_event = {
                "person_id": db_id if db_id is not None else (person_id if person_id is not None else -1),
                "event_type": EVENTS[0],
                "score": recognition_score,
            }
        elif self._unknown_face_event_enabled():
            best_score = float(results[0].get("score", 0.0)) if results else 0.0
            pending_event = {
                "person_id": None,
                "event_type": EVENT_UNKNOWN_FACE,
                "score": best_score,
            }

        record = {
            "track_id": track_id, "name": name, "score": recognition_score,
            "person_id": person_id, "db_id": db_id, "from_cache": False,
            "is_blacklisted": is_blacklisted, "frame_idx": frame_idx,
            "vote_pending": False,
        }
        return record, pending_event

    @staticmethod
    def _face_vote(observations: List[Tuple]) -> Optional[Tuple]:
        """Consensus d'identité sur les observations FAISS accumulées d'un track.

        observations : liste de (db_id, name, score, is_blacklisted, quality) — une
        par frame. Candidat retenu = db_id le PLUS souvent renvoyé (départage par
        masse de score PONDÉRÉE par la qualité). Le score représentatif est la
        moyenne du cosine PONDÉRÉE par la qualité : les bonnes frames (frontales,
        grandes, nettes) tirent la décision, les mauvaises pèsent peu (best-shot).
        Si toutes les qualités valent 1.0, on retombe sur la moyenne simple
        d'origine (aucune régression).

        Returns:
            (db_id, name, is_blacklisted, n_accords, score_moyen_pondéré) ou None si
            aucune observation exploitable.
        """
        counts: Dict = defaultdict(int)
        wsum: Dict = defaultdict(float)    # somme des poids (qualité) par candidat
        wscore: Dict = defaultdict(float)  # somme de score × qualité par candidat
        meta: Dict = {}
        for obs in observations:
            db_id, name, score, bl = obs[0], obs[1], obs[2], obs[3]
            q = obs[4] if len(obs) > 4 and obs[4] is not None else 1.0
            if db_id is None:
                continue
            w = max(float(q), 1e-6)   # poids strictement positif (jamais d'annulation)
            counts[db_id] += 1
            wsum[db_id] += w
            wscore[db_id] += float(score) * w
            meta[db_id] = (name, bool(bl))   # mémorise le dernier nom/statut vus
        if not counts:
            return None
        # Gagnant choisi par MASSE DE QUALITÉ (somme des poids), pas par simple
        # comptage : 2 frames médiocres (faux positif probable) ne battent pas
        # 1 bonne frame. Départage par masse de score pondérée. Si toutes les
        # qualités valent 1.0, wsum == counts → sélection identique à l'ancienne.
        best = max(counts.keys(), key=lambda k: (wsum[k], wscore[k]))
        agree = counts[best]   # accords BRUTS : conserve la sémantique de MIN_AGREE
        mean_score = wscore[best] / wsum[best]   # moyenne du cosine pondérée qualité
        name, bl = meta[best]
        return best, name, bl, agree, mean_score

    def _decide_fresh_voted(self, item: Dict, results: List, frame_idx: int,
                            expected) -> Tuple[Dict, Optional[Dict]]:
        """ÉTAPE 2 (vote temporel) — accumule les décisions FAISS le long du track
        et ne CONFIRME une identité qu'au consensus (même personne ≥ MIN_AGREE fois,
        score moyen ≥ seuil). Tant que non confirmé : record « Inconnu » + vote_pending
        (le thread caméra ré-interroge à la frame suivante). Au-delà de MAX_ATTEMPTS
        sans consensus → figé « Inconnu ». Symétrique de PlateProcessor._apply_reading."""
        track_id = item["track_id"]
        embedding = item["embedding"]

        vs = self._vote_state.get(track_id)
        if vs is None:
            vs = {"obs": [], "attempts": 0, "last_frame": frame_idx}
            self._vote_state[track_id] = vs
        vs["last_frame"] = frame_idx
        vs["attempts"] += 1

        threshold = self.adaptive_threshold.value

        if results:
            api_score = float(results[0].get("score", 0.0))
            api_name = results[0].get("name", "?")
            api_db_id = results[0].get("id")
            api_bl = bool(results[0].get("is_blacklisted", False))
            self.adaptive_threshold.observe(api_score)
            if api_score > 0.0 and api_score < 0.05:
                logger.warning(
                    f"[track_id={track_id}] Score anormalement bas ({api_score:.4f}) — "
                    "vérifier la normalisation L2 des embeddings (norme != 1.0 ?)"
                )
            # Métrique brute par observation (préserve les données EER : 1 score
            # FAISS frais par frame, `accepted` = décision mono-frame indicative).
            emit_recognition_metric(
                camera_id=self.cam_id,
                camera_name=self.cam_name,
                track_id=track_id,
                cosine_score=api_score,
                adaptive_threshold=threshold,
                accepted=(api_score > threshold),
                candidate_name=api_name,
                from_cache=False,
                expected=expected,
            )
            vs["obs"].append((api_db_id, api_name, api_score, api_bl, item.get("quality", 1.0)))
        else:
            logger.warning(
                f"[track_id={track_id}] API search : aucun résultat retourné "
                f"(index FAISS vide ou erreur réseau) [cam={self.cam_name}]"
            )

        cand = self._face_vote(vs["obs"])
        confirmed = (cand is not None
                     and cand[3] >= self.face_vote_min_agree
                     and cand[4] >= threshold)
        exhausted = vs["attempts"] >= self.face_vote_max_attempts

        name = "Inconnu"
        recognition_score = 0.0
        person_id = None
        db_id = None
        is_blacklisted = False
        vote_pending = False
        pending_event = None

        if confirmed or exhausted:
            if confirmed:
                db_id = cand[0]
                name = cand[1]
                is_blacklisted = cand[2]
                recognition_score = cand[4]
                bl = self.blacklist_cache.is_blacklisted(db_id)
                if bl is not None:
                    is_blacklisted = bl
                if self.global_tracker and embedding is not None:
                    person_id = self.global_tracker.find_or_register(
                        name=name, embedding=embedding, camera_id=self.cam_id,
                        track_id=track_id, recognition_score=recognition_score,
                        is_blacklisted=is_blacklisted, db_id=db_id,
                    )
                logger.info(
                    f"[track_id={track_id}] VOTE CONFIRMÉ → {name!r} "
                    f"score_moyen={recognition_score:.4f} accords={cand[3]}/{vs['attempts']} "
                    f"seuil={threshold:.4f} [cam={self.cam_name}]"
                )
                pending_event = {
                    "person_id": db_id if db_id is not None else (person_id if person_id is not None else -1),
                    "event_type": EVENTS[0],
                    "score": recognition_score,
                }
            else:
                logger.info(
                    f"[track_id={track_id}] VOTE NON CONCLUANT après {vs['attempts']} "
                    f"tentatives → Inconnu [cam={self.cam_name}]"
                )
                if self._unknown_face_event_enabled():
                    best_score = max((o[2] for o in vs["obs"]), default=0.0)
                    pending_event = {
                        "person_id": None,
                        "event_type": EVENT_UNKNOWN_FACE,
                        "score": best_score,
                    }
            self._vote_state.pop(track_id, None)
        else:
            # Toujours en cours de vote : on garde « Inconnu » et on demande au thread
            # caméra de ré-interroger ce track à la prochaine frame traitée.
            vote_pending = True

        record = {
            "track_id": track_id, "name": name, "score": recognition_score,
            "person_id": person_id, "db_id": db_id, "from_cache": False,
            "is_blacklisted": is_blacklisted, "frame_idx": frame_idx,
            "vote_pending": vote_pending,
        }
        return record, pending_event

    async def _send_events(self, pending_events: List[Dict], session: aiohttp.ClientSession,
                           frame: np.ndarray) -> None:
        """Envoie tous les événements du batch en parallèle (sur le thread worker).

        Chaque événement porte son propre `event_type` (RECOGNITION pour un visage
        reconnu, UNKNOWN_FACE pour un visage non reconnu) et son `person_id`
        (None → champ omis, person_id NULL côté backend)."""
        tasks = [
            send_event_async(
                session, frame, self.cam_id,
                ev["person_id"], ev.get("event_type", EVENTS[0]), ev["score"]
            )
            for ev in pending_events
        ]
        outcomes = await asyncio.gather(*tasks, return_exceptions=True)
        for ev, outcome in zip(pending_events, outcomes):
            if isinstance(outcome, Exception):
                logger.warning(
                    f"Échec envoi événement pour person_id={ev['person_id']}: {outcome}"
                )

    # Phase 2 : annotate_frame()/add_camera_overlay() SUPPRIMÉS. Le Core ne dessine
    # plus sur la frame ; il publie des bounding boxes JSON (cf. run() → result_metadata)
    # que le frontend superpose sur la vidéo WebRTC via un <canvas>.

    def cleanup_cache(self, frame_idx: int):
        """Nettoie le cache des tracks expirés"""
        if frame_idx % self.config.REIDENTIFICATION_INTERVAL == 0:
            expired = [tid for tid, data in self.person_db.items()
                       if frame_idx - data["last_updated"] > self.config.CACHE_TTL_FRAMES]
            for tid in expired:
                del self.person_db[tid]
            # Purge des files de fusion d'embeddings des tracks disparus (borne la
            # mémoire). Possédé par ce seul thread caméra → pas de verrou.
            ttl = self.config.CACHE_TTL_FRAMES
            stale_hist = [tid for tid, last in self._embedding_last_frame.items()
                          if frame_idx - last > ttl]
            for tid in stale_hist:
                self._embedding_history.pop(tid, None)
                self._embedding_last_frame.pop(tid, None)
            if self.global_tracker:
                cleaned_count = self.global_tracker.cleanup_expired_entries()
                if cleaned_count > 0:
                    logger.debug(f"{cleaned_count} entrées expirées nettoyées du cache global")

    @staticmethod
    def _compute_frame_sharpness(frame: np.ndarray) -> float:
        """
        Variance du Laplacien sur la luminance — mesure de netteté de frame.
        Seuils empiriques sur RTSP 640×480 H.264 :
          < 40  → très flou (bougé caméra)
          40-80 → flou modéré (mouvement rapide)
          > 80  → acceptable pour ArcFace embedding
        Coût : ~0.3ms sur CPU (negligeable vs 15-30ms pour SCRFD).
        """
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        return float(cv2.Laplacian(gray, cv2.CV_64F).var())

    # ──────────────────────────────────────────────────────────────────────
    # Mesure de latence (chapitre 4) — alimenté par run(), lu par le sampler
    # ──────────────────────────────────────────────────────────────────────
    def _record_latency(self, face_ms: Optional[float],
                        frame_ms: Optional[float] = None) -> None:
        """Enregistre la latence d'inférence d'une frame traitée (thread caméra)."""
        with self._lat_lock:
            if face_ms is not None:
                self._face_ms.append(face_ms)
            if frame_ms is not None:
                self._frame_ms.append(frame_ms)

    def latency_snapshot(self, reset: bool = True) -> Dict:
        """Instantané des latences depuis le dernier appel (fenêtre non chevauchante).

        Retourne le nombre de frames traitées et les p50/p95/moyenne (ms) pour le
        facial. `reset` vide les accumulateurs →
        l'échantillon suivant ne couvre que l'intervalle écoulé (le sampler en
        déduit aussi le débit réel : n / durée d'intervalle).
        """
        with self._lat_lock:
            face = list(self._face_ms)
            frame = list(self._frame_ms)
            if reset:
                self._face_ms.clear()
                self._frame_ms.clear()

        def _stats(a):
            if not a:
                return {"p50": None, "p95": None, "mean": None}
            arr = np.asarray(a, dtype=float)
            return {
                "p50": round(float(np.percentile(arr, 50)), 2),
                "p95": round(float(np.percentile(arr, 95)), 2),
                "mean": round(float(arr.mean()), 2),
            }

        return {
            "n_face": len(face),
            "n_frame": len(frame),
            "face_ms": _stats(face),
            # Coût TOTAL par frame traitée. overhead CPU ≈ frame_ms − face_ms
            # (tracker, gating, build JSON) → permet de trancher GPU-bound vs CPU-bound.
            "frame_ms": _stats(frame),
        }

    def apply_effective_config(self, facial_active: bool) -> None:
        """Applique À CHAUD la config effective (facial) de CETTE caméra.

        Appelée par la boucle de supervision quand la config effective change
        (bascule de groupe ou drapeau local). Ne redémarre PAS le thread : le
        prochain tour de boucle lit simplement les nouveaux drapeaux et saute
        l'étape désactivée, libérant immédiatement les ressources GPU/CPU.
        """
        facial_active = bool(facial_active)
        if facial_active != self._effective_facial_active:
            logger.info(
                f"[cam={self.cam_name}] pipeline FACIAL "
                f"{'activé' if facial_active else 'désactivé'} à chaud (config groupe/caméra)."
            )
            self._effective_facial_active = facial_active

    def _unknown_face_event_enabled(self) -> bool:
        """Événement « visage non reconnu » actif ? Priorité au drapeau runtime
        (toggle frontend), sinon valeur de config."""
        if self.runtime_control is not None:
            return self.runtime_control.unknown_face_event_enabled
        return getattr(self.config, 'ENABLE_UNKNOWN_FACE_EVENT', False)

    def _face_recognition_enabled(self) -> bool:
        """Reconnaissance faciale active pour CETTE caméra ?

        Combinaison en ET : (1) toggle runtime GLOBAL (système), (2) config
        effective PAR CAMÉRA (drapeau local ∧ tous ses groupes). DÉFAUT = True
        aux deux niveaux → aucune régression. Désactiver le facial pour un groupe
        coupe SCRFD/ArcFace et la file de reconnaissance ici, libérant le GPU."""
        if not self._effective_facial_active:
            return False
        if self.runtime_control is not None:
            return self.runtime_control.face_recognition_enabled
        return getattr(self.config, 'ENABLE_FACE_RECOGNITION', True)

    def run(self):
        """Boucle principale de traitement"""
        # Plus aucune boucle asyncio / session HTTP sur le thread caméra : toute
        # la résolution réseau (recherche FAISS + événement) vit dans le worker
        # dédié ci-dessous, en fire-and-forget. Le thread caméra ne fait que de la
        # vision et la publication de métadonnées JSON (aucun encodage/dessin vidéo).
        self.loop = None        # conservé pour compat. de signature
        self._session = None
        self._recognition_worker = threading.Thread(
            target=self._recognition_loop,
            name=f"recognition-{self.cam_id}",
            daemon=True,
        )
        self._recognition_worker.start()

        try:
            while not self.stop_event.is_set():
                try:
                    frame = self.frame_queue.get(timeout=self.config.FRAME_QUEUE_TIMEOUT)
                except queue.Empty:
                    continue

                self.frame_counter += 1
                self.frame_idx_container[self.cam_id] += 1
                frame_idx = self.frame_idx_container[self.cam_id]

                # Appliquer les reconnaissances revenues du worker (écrit person_db
                # sur CE thread uniquement) avant d'annoter cette frame.
                self._drain_recognition_results()

                # On ne calcule des détections que sur 1 frame sur N (cadence GPU).
                # Entre deux, l'overlay frontend conserve les dernières boxes — la
                # vidéo WebRTC reste fluide à pleine cadence, servie par MediaMTX.
                if self.frame_counter % self.config.PROCESS_EVERY_N_FRAME != 0:
                    continue

                # Quality gate : rejeter les frames trop floues AVANT l'inférence GPU.
                # Coût : ~0.3ms vs 15-30ms pour SCRFD. L'overlay précédent persiste.
                blur_threshold = getattr(self.config, 'BLUR_THRESHOLD', 80.0)
                if blur_threshold > 0:
                    sharpness = self._compute_frame_sharpness(frame)
                    if sharpness < blur_threshold:
                        self._blur_skip_count += 1
                        if self._blur_skip_count % 30 == 1:  # log 1/30 pour éviter le spam
                            logger.debug(
                                f"[cam={self.cam_name}] Frame floue rejetée "
                                f"(Laplacien={sharpness:.1f} < seuil={blur_threshold:.1f}, "
                                f"total rejetées=#{self._blur_skip_count})"
                            )
                            emit_blur_metric(
                                camera_id=self.cam_id,
                                camera_name=self.cam_name,
                                sharpness=sharpness,
                                threshold=blur_threshold,
                                total_skipped=self._blur_skip_count,
                            )
                        continue  # pas d'inférence ; l'overlay précédent reste affiché

                # Détections de cette frame (visages) publiées en JSON.
                # Déclaré AVANT le gate facial → toujours défini pour le payload.
                detections: List[Dict] = []

                # Mesure (chapitre 4) : latences de cette frame traitée.
                face_ms: Optional[float] = None
                _t_frame = time.perf_counter()   # coût total de traitement de la frame

                # ── Pipeline FACIAL — activable/désactivable À CHAUD ──────────────
                # Désactivé : on saute SCRFD/ArcFace + la reconnaissance (GPU non
                # sollicité pour les visages) et aucune box visage n'est produite.
                # Le blur-gate et la publication des métadonnées (plus bas)
                # restent inchangés → couper le facial ne casse rien d'autre.
                if self._face_recognition_enabled():
                    # Single GPU pass: SCRFD detection + alignment + ArcFace embedding.
                    # 1re valeur de retour ignorée : on ne dessine plus (overlay côté client).
                    _t_face = time.perf_counter()
                    _, faces_data = detect_faces_with_embeddings(
                        frame, confidence_threshold=self.config.FACE_DETECTION_CONFIDENCE
                    )
                    face_ms = (time.perf_counter() - _t_face) * 1000.0

                    output_results, faces_indexed = self.prepare_detections(faces_data)
                    img_info = [frame.shape[0], frame.shape[1]]
                    tracks = self.tracker.update(output_results, img_info, img_info)

                    # Reconnaissances (fire-and-forget) — pas de re-soumission d'un track
                    # déjà en cours de résolution (anti-spam : _recognition_inflight).
                    job_items = []
                    for track in tracks:
                        track_id = track.track_id
                        if (self.should_recognize_track(track_id, frame_idx)
                                and track_id not in self._recognition_inflight):
                            embedding, bbox, frontality = self.find_best_embedding_for_track(track, faces_indexed)
                            if embedding is None:
                                continue
                            # ── Garde-fou de taille : on ne tente PAS de reconnaître
                            # un visage plus petit que FACE_MIN_RECOG_SIZE (px, plus
                            # petit côté) — embedding ArcFace dégradé → décision peu
                            # fiable. Le track reste affiché « Inconnu » (la box est
                            # quand même produite plus bas). Symétrique du gating LPR.
                            if self.face_min_size > 0 and min(bbox[2], bbox[3]) < self.face_min_size:
                                self._face_gated_count += 1
                                if self._face_gated_count % 30 == 1:
                                    logger.debug(
                                        f"[cam={self.cam_name}] visage trop petit pour "
                                        f"reconnaissance : {bbox[2]}×{bbox[3]}px < "
                                        f"{self.face_min_size}px (total gatés=#{self._face_gated_count})"
                                    )
                                continue
                            # ── Garde-fou de frontalité : on n'interroge pas un profil
                            # extrême (embedding ArcFace peu fiable). Le track reste
                            # « Inconnu » et sera rattrapé quand la personne se tourne.
                            if self.face_min_frontality > 0.0 and frontality < self.face_min_frontality:
                                self._face_profile_gated += 1
                                if self._face_profile_gated % 30 == 1:
                                    logger.debug(
                                        f"[cam={self.cam_name}] visage trop de profil pour "
                                        f"reconnaissance : frontalité={frontality:.2f} < "
                                        f"{self.face_min_frontality:.2f} (total gatés=#{self._face_profile_gated})"
                                    )
                                continue
                            # ── Netteté CIBLÉE sur le crop du visage (complète le
                            # BLUR_THRESHOLD qui porte sur la frame entière). Calculée
                            # UNE seule fois ici, réutilisée par le gate dur ET par le
                            # score de qualité best-shot ci-dessous.
                            crop_sharp = None
                            if self.face_crop_min_sharpness > 0.0 or self.face_quality_weighting:
                                crop_sharp = self._crop_sharpness(frame, bbox)
                            # Gate dur : un visage flou sur fond net → embedding dégradé.
                            if (self.face_crop_min_sharpness > 0.0 and crop_sharp is not None
                                    and crop_sharp < self.face_crop_min_sharpness):
                                self._face_blur_gated += 1
                                if self._face_blur_gated % 30 == 1:
                                    logger.debug(
                                        f"[cam={self.cam_name}] visage flou pour "
                                        f"reconnaissance : netteté_crop={crop_sharp:.1f} < "
                                        f"{self.face_crop_min_sharpness:.1f} (total gatés=#{self._face_blur_gated})"
                                    )
                                continue
                            # ── Best-shot : qualité ∈ [0,1] du visage → pondère le vote
                            # temporel pour que les BONNES frames décident l'identité.
                            quality = (self._face_quality(bbox, frontality, crop_sharp)
                                       if self.face_quality_weighting else 1.0)
                            # ── Fusion temporelle : la requête FAISS n'est plus
                            # l'embedding mono-frame mais la moyenne re-normalisée des
                            # derniers embeddings de ce track (plus stable, score plus
                            # haut). Maintenu sur CE thread (producteur unique).
                            query_embedding = self._fused_embedding(track_id, embedding, frame_idx)
                            job_items.append({
                                "track_id": track_id,
                                "x": bbox[0], "y": bbox[1], "w": bbox[2], "h": bbox[3],
                                "embedding": query_embedding,
                                "quality": quality,
                            })
                    if job_items:
                        self._submit_recognition(job_items, frame_idx, frame)

                    # ── Détections faciales → JSON (aucun dessin) ──
                    for track in tracks:
                        track_id = track.track_id
                        tlwh = track.tlwh
                        x, y, w, h = int(tlwh[0]), int(tlwh[1]), int(tlwh[2]), int(tlwh[3])
                        cached = self.person_db.get(track_id)
                        blacklisted = bool(cached.get("is_blacklisted")) if cached else False
                        # Réévaluation LIVE du statut « surveillance » : un (dé)blacklist
                        # est pris en compte au prochain rafraîchissement du poll backend
                        # (~5s), sans attendre la ré-identification du track.
                        if cached:
                            bl = self.blacklist_cache.is_blacklisted(cached.get("db_id"))
                            if bl is not None:
                                blacklisted = bl
                        if cached and cached["name"] != "Inconnu":
                            recognized = True
                            score = cached["score"]
                            label = f'{cached["name"]} {score:.0%}' if score > 0 else cached["name"]
                            if blacklisted:
                                label = f'⚠ {label} [BLACKLIST]'
                        else:
                            recognized = False
                            label = "Inconnu"
                        detections.append({
                            "type": "face",
                            "track_id": track_id,
                            "bbox": [x, y, x + w, y + h],
                            "label": label,
                            "recognized": recognized,
                            # alert=True → personne sur liste de surveillance (toast/son + overlay rouge)
                            "alert": blacklisted,
                        })

                    self.cleanup_cache(frame_idx)

                # ── Mesure : enregistrer les latences de cette frame traitée ──
                frame_ms = (time.perf_counter() - _t_frame) * 1000.0
                self._record_latency(face_ms, frame_ms)

                # ── Publier le payload de métadonnées (overlay frontend) ──
                # Les bbox sont exprimées dans le repère de la frame traitée
                # (width×height) ; le frontend les met à l'échelle vers la taille
                # d'affichage réelle de l'élément <video>.
                fh, fw = frame.shape[:2]
                payload = {
                    "camera_id": self.cam_id,
                    "width": fw,
                    "height": fh,
                    "detections": detections,
                }
                with self.result_lock:
                    self.result_metadata[self.cam_id] = {"seq": frame_idx, "payload": payload}

        finally:
            # Arrêt propre du worker réseau facial (thread + boucle/sessions dédiées).
            try:
                self._recognition_jobs.put_nowait(None)   # réveille le worker s'il attend
            except Exception:
                pass
            if self._recognition_worker is not None and self._recognition_worker.is_alive():
                self._recognition_worker.join(timeout=3)

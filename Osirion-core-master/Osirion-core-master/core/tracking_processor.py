# core/tracking_processor.py
"""
Traitement de la détection, du tracking et de la reconnaissance faciale
"""
import cv2
import numpy as np
import asyncio
import aiohttp
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

logger = get_logger(__name__)

# Type d'événement émis pour un visage détecté mais NON reconnu (opt-in).
# Doit rester aligné sur backend app/models/events.py::EVENT_UNKNOWN_FACE.
EVENT_UNKNOWN_FACE = "UNKNOWN_FACE"


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

        # ── LPR / ANPR (module plaques, optionnel et indépendant du facial) ──
        self.runtime_control = runtime_control      # drapeau activable au runtime
        self._cam = cam                             # mémorisé pour init paresseuse
        self.plate_processor = None                 # créé à la 1re activation LPR
        self._lpr_init_failed = False               # évite de réessayer en boucle

        self.frame_counter = 0
        self.loop = None
        self._session = None
        self._blur_skip_count = 0  # compteur de frames rejetées pour flou (monitoring)

        # ── Worker réseau découplé pour la reconnaissance faciale ────────────
        # Le thread caméra ne bloque JAMAIS sur le réseau : il pousse un job
        # (embeddings + snapshot) dans _recognition_jobs et continue immédiatement.
        # Un thread dédié (_recognition_loop) fait la recherche FAISS + l'envoi
        # d'événement, puis renvoie les résultats via _recognition_results. Le
        # thread caméra applique ces résultats à person_db (toutes les écritures
        # de person_db restent sur le thread caméra → pas de verrou nécessaire).
        # Même patron que PlateProcessor (cf. core/plate_processor.py).
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

    def prepare_detections(self, faces_data: List) -> Tuple[np.ndarray, List]:
        """Prépare les détections pour ByteTrack. Chaque entrée porte déjà son embedding GPU."""
        detections = []
        faces_indexed = []
        for (x, y, w, h), conf, embedding in faces_data:
            if embedding is None:
                continue
            x1, y1, x2, y2 = x, y, x + w, y + h
            detections.append([x1, y1, x2, y2, conf])
            faces_indexed.append((embedding, (x, y, w, h), conf))
        return np.array(detections) if detections else np.empty((0, 5)), faces_indexed

    def find_best_embedding_for_track(self, track, faces_indexed: List):
        """Retourne l'embedding le plus proche du centre du track (distance euclidienne 2D)."""
        tlwh = track.tlwh
        x, y, w, h = int(tlwh[0]), int(tlwh[1]), int(tlwh[2]), int(tlwh[3])
        center_x = x + w // 2
        center_y = y + h // 2

        best_embedding = None
        best_dist = float('inf')
        for embedding, bbox, _ in faces_indexed:
            bx, by, bw, bh = bbox
            bc_x, bc_y = bx + bw // 2, by + bh // 2
            dist = (bc_x - center_x)**2 + (bc_y - center_y)**2
            if dist < best_dist:
                best_dist = dist
                best_embedding = embedding
        return best_embedding, (x, y, w, h)

    def should_recognize_track(self, track_id: int, frame_idx: int) -> bool:
        """Détermine si un track doit être reconnu"""
        return (track_id not in self.person_db or
                self.person_db[track_id].get("last_updated", -1000) < frame_idx - self.config.REIDENTIFICATION_INTERVAL)

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
        """Décide l'identité d'un track (cache global → API + seuil adaptatif).

        Exécuté sur le thread worker. N'écrit PAS person_db (renvoie un
        enregistrement appliqué ensuite par le thread caméra). global_tracker est
        thread-safe ; adaptive_threshold n'est touché que par ce worker.
        """
        track_id = item["track_id"]
        embedding = item["embedding"]

        name = "Inconnu"
        recognition_score = 0.0
        person_id = None
        db_id = None
        from_cache = False
        is_blacklisted = False
        old_blacklisted = False   # statut mémorisé avant rafraîchissement (cache hit)

        # ÉTAPE 1 : Vérifier le cache global AVANT l'API
        if self.global_tracker and embedding is not None:
            cached_match = self.global_tracker.find_person_by_embedding(embedding, self.cam_id)
            if cached_match:
                name = cached_match["name"]
                recognition_score = cached_match["score"]
                person_id = cached_match["person_id"]
                db_id = cached_match.get("db_id")
                is_blacklisted = bool(cached_match.get("is_blacklisted", False))
                old_blacklisted = is_blacklisted
                # Statut « surveillance » FRAIS prioritaire : un (dé)blacklist récent
                # prime sur le flag mémorisé dans le cache global (potentiellement périmé).
                bl = self.blacklist_cache.is_blacklisted(db_id)
                if bl is not None:
                    is_blacklisted = bl
                    if bl != old_blacklisted and person_id is not None:
                        # Propage le changement (montée OU descente) dans le cache
                        # global → les ré-identifications suivantes voient le bon
                        # statut et ne ré-émettent pas d'alerte.
                        self.global_tracker.set_blacklist_status(person_id, bl)
                from_cache = True
                self.global_tracker.update_person_location(person_id, self.cam_id, track_id)
                logger.info(
                    f"✓ Cache global : {name} — score={recognition_score:.2f} ({recognition_score:.0%})"
                    f" [cam={self.cam_name}, track_id={track_id}]"
                )

        # ÉTAPE 2 : Si pas en cache, utiliser les résultats de l'API
        if not from_cache:
            if not results:
                logger.warning(
                    f"[track_id={track_id}] API search : aucun résultat retourné "
                    f"(index FAISS vide ou erreur réseau) [cam={self.cam_name}]"
                )
            else:
                api_score = results[0].get("score", 0)
                api_name  = results[0].get("name", "?")
                current_threshold = self.adaptive_threshold.value
                # Alimenter le seuil adaptatif avec chaque score observé
                self.adaptive_threshold.observe(api_score)
                accepted = api_score > current_threshold

                # Alerte si score hors range attendu [0.05, 0.95] — indique un problème de normalisation
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

                # Métrique structurée pour monitoring production
                emit_recognition_metric(
                    camera_id=self.cam_id,
                    camera_name=self.cam_name,
                    track_id=track_id,
                    cosine_score=api_score,
                    adaptive_threshold=current_threshold,
                    accepted=accepted,
                    candidate_name=api_name,
                    from_cache=False,
                )

        pending_event = None
        if not from_cache and results and results[0].get("score", 0) > self.adaptive_threshold.value:
            name = results[0].get("name", "Inconnu")
            recognition_score = results[0].get("score", 0.0)
            db_id = results[0].get("id")
            is_blacklisted = bool(results[0].get("is_blacklisted", False))
            # Statut frais prioritaire (gère blacklist ET déblacklist, même si la
            # recherche locale/HTTP renvoyait une valeur légèrement en retard).
            bl = self.blacklist_cache.is_blacklisted(db_id)
            if bl is not None:
                is_blacklisted = bl

            if self.global_tracker and embedding is not None:
                person_id = self.global_tracker.find_or_register(
                    name=name,
                    embedding=embedding,
                    camera_id=self.cam_id,
                    track_id=track_id,
                    recognition_score=recognition_score,
                    is_blacklisted=is_blacklisted,
                    db_id=db_id,
                )

            # Événement « fire-and-forget » : envoyé par le worker après coup.
            # person_id = identifiant BACKEND (People.id) → le hook d'alerte backend
            # (_maybe_create_alert) résout la bonne personne.
            pending_event = {
                "person_id": db_id if db_id is not None else (person_id if person_id is not None else -1),
                "event_type": EVENTS[0],            # "RECOGNITION" (comportement inchangé)
                "score": recognition_score,
            }
        elif from_cache and is_blacklisted and not old_blacklisted:
            # TRANSITION non-surveillé → surveillé d'une personne DÉJÀ suivie (cache
            # hit) : on émet UNE alerte RECOGNITION pour que le backend la crée, sans
            # attendre l'expiration du cache. Pas de spam : le statut vient d'être
            # mémorisé (set_blacklist_status), donc les ré-identifications suivantes
            # ne repassent plus par cette transition.
            pending_event = {
                "person_id": db_id if db_id is not None else (person_id if person_id is not None else -1),
                "event_type": EVENTS[0],
                "score": recognition_score,
            }
        elif not from_cache and self._unknown_face_event_enabled():
            # Visage DÉTECTÉ mais NON reconnu (aucun match au-dessus du seuil et
            # absent du cache global) → événement DISTINCT, sans person_id.
            # OPT-IN : ne se déclenche que si le toggle est activé. N'altère ni la
            # reconnaissance ni l'overlay (name reste "Inconnu"). Le throttling de
            # la ré-identification borne la fréquence (≤ 1 / track / intervalle).
            best_score = float(results[0].get("score", 0.0)) if results else 0.0
            pending_event = {
                "person_id": None,
                "event_type": EVENT_UNKNOWN_FACE,
                "score": best_score,
            }

        record = {
            "track_id": track_id,
            "name": name,
            "score": recognition_score,
            "person_id": person_id,
            "db_id": db_id,
            "from_cache": from_cache,
            "is_blacklisted": is_blacklisted,
            "frame_idx": frame_idx,
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

    def _lpr_enabled(self) -> bool:
        """LPR actif ? Priorité au drapeau runtime (toggle frontend), sinon config."""
        if self.runtime_control is not None:
            return self.runtime_control.lpr_enabled
        return getattr(self.config, 'ENABLE_PLATE_RECOGNITION', False)

    def _unknown_face_event_enabled(self) -> bool:
        """Événement « visage non reconnu » actif ? Priorité au drapeau runtime
        (toggle frontend), sinon valeur de config."""
        if self.runtime_control is not None:
            return self.runtime_control.unknown_face_event_enabled
        return getattr(self.config, 'ENABLE_UNKNOWN_FACE_EVENT', False)

    def _face_recognition_enabled(self) -> bool:
        """Reconnaissance faciale active ? Priorité au drapeau runtime (toggle
        frontend), sinon config. DÉFAUT = True (pipeline principal) : sans
        runtime_control ni config, le facial reste ACTIVÉ → aucune régression."""
        if self.runtime_control is not None:
            return self.runtime_control.face_recognition_enabled
        return getattr(self.config, 'ENABLE_FACE_RECOGNITION', True)

    def _ensure_plate_processor(self):
        """Crée le PlateProcessor à la 1re activation (chargement modèles paresseux)."""
        if self.plate_processor is not None or self._lpr_init_failed:
            return self.plate_processor
        try:
            from core.plate_processor import PlateProcessor
            logger.info(f"[LPR][cam={self.cam_name}] Initialisation du module plaques...")
            self.plate_processor = PlateProcessor(self._cam, self.config)
        except Exception as e:
            self._lpr_init_failed = True
            logger.error(
                f"[LPR][cam={self.cam_name}] Init impossible — LPR désactivé pour cette "
                f"caméra (le pipeline facial continue normalement) : {e}"
            )
        return self.plate_processor

    def _collect_plate_detections(self, frame: np.ndarray, frame_idx: int) -> List[Dict]:
        """Lance le pipeline LPR (détection + OCR, SANS dessin) et renvoie les
        détections plaques au format JSON pour l'overlay frontend."""
        if not self._lpr_enabled():
            return []
        pp = self._ensure_plate_processor()
        if pp is None:
            return []
        try:
            pp.process(frame, frame_idx)        # met à jour plate_db (aucun dessin)
            return pp.get_detections()          # bounding boxes plaques en JSON
        except Exception as e:
            logger.error(f"[LPR][cam={self.cam_name}] erreur pipeline plaques : {e}")
            return []

    def run(self):
        """Boucle principale de traitement"""
        # Plus aucune boucle asyncio / session HTTP sur le thread caméra : toute
        # la résolution réseau (recherche FAISS + événement) vit dans le worker
        # dédié ci-dessous, en fire-and-forget. Le thread caméra ne fait que de la
        # vision et la publication de métadonnées JSON (aucun encodage/dessin vidéo).
        self.loop = None        # conservé pour compat. de signature (LPR l'ignore)
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

                # Détections de cette frame (visages + plaques) publiées en JSON.
                # Déclaré AVANT le gate facial → toujours défini pour le LPR + payload.
                detections: List[Dict] = []

                # ── Pipeline FACIAL — activable/désactivable À CHAUD ──────────────
                # Désactivé : on saute SCRFD/ArcFace + la reconnaissance (GPU non
                # sollicité pour les visages) et aucune box visage n'est produite.
                # Le LPR, le blur-gate et la publication des métadonnées (plus bas)
                # restent inchangés → couper le facial ne casse rien d'autre.
                if self._face_recognition_enabled():
                    # Single GPU pass: SCRFD detection + alignment + ArcFace embedding.
                    # frame_annotated est ignoré : on ne dessine plus (overlay côté client).
                    _, faces_data = detect_faces_with_embeddings(
                        frame, confidence_threshold=self.config.FACE_DETECTION_CONFIDENCE
                    )

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
                            embedding, bbox = self.find_best_embedding_for_track(track, faces_indexed)
                            if embedding is not None:
                                job_items.append({
                                    "track_id": track_id,
                                    "x": bbox[0], "y": bbox[1], "w": bbox[2], "h": bbox[3],
                                    "embedding": embedding,
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

                # ── LPR : détection + lecture des plaques → détections JSON ──
                detections.extend(self._collect_plate_detections(frame, frame_idx))

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

            # Arrêt propre du worker réseau LPR (thread + session aiohttp dédiés).
            if self.plate_processor is not None:
                try:
                    self.plate_processor.shutdown()
                except Exception as e:
                    logger.debug(f"[LPR][cam={self.cam_name}] arrêt worker LPR : {e}")

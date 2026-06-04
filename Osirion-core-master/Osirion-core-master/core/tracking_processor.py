# core/tracking_processor.py
"""
Traitement de la détection, du tracking et de la reconnaissance faciale
"""
import cv2
import numpy as np
import asyncio
import aiohttp
from typing import Dict, List, Tuple
import queue

from face_detection import detect_faces_with_embeddings
from services.embeddings_search_service import search_embedding_async
from services.event_services import send_event_async
from config.settings import EVENTS
from core.adaptive_threshold import AdaptiveThreshold
from utils.logger import get_logger
from utils.monitoring import emit_recognition_metric, emit_blur_metric

logger = get_logger(__name__)


class TrackingProcessor:
    """Gère le traitement de détection, tracking et reconnaissance pour une caméra"""

    def __init__(self, cam: Dict, frame_queue: queue.Queue, result_frames: Dict,
                 result_lock, tracker, person_db: Dict, frame_idx_container: Dict,
                 stop_event, config, global_tracker=None, runtime_control=None):
        self.cam_id = cam["id"]
        self.cam_name = cam["cam_name"]
        self.location = cam["location"]
        self.frame_queue = frame_queue
        self.result_frames = result_frames
        self.result_lock = result_lock
        self.tracker = tracker
        self.person_db = person_db
        self.frame_idx_container = frame_idx_container
        self.stop_event = stop_event
        self.config = config
        self.global_tracker = global_tracker

        # ── LPR / ANPR (module plaques, optionnel et indépendant du facial) ──
        self.runtime_control = runtime_control      # drapeau activable au runtime
        self._cam = cam                             # mémorisé pour init paresseuse
        self.plate_processor = None                 # créé à la 1re activation LPR
        self._lpr_init_failed = False               # évite de réessayer en boucle

        self.frame_counter = 0
        self.loop = None
        self._session = None
        self._last_bboxes: Dict[int, Tuple] = {}
        self._blur_skip_count = 0  # compteur de frames rejetées pour flou (monitoring)

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

    async def process_recognitions(self, recognition_tasks: List, session: aiohttp.ClientSession) -> List:
        """Exécute toutes les reconnaissances en parallèle"""
        # Fix #3 : track_info était déclaré mais jamais utilisé — supprimé
        tasks = [search_embedding_async(session, emb, top_k=1) for emb in recognition_tasks]
        return await asyncio.gather(*tasks)

    async def update_person_database(self, track_info: List, results_list: List, frame_idx: int,
                                     embeddings_list: List, session: aiohttp.ClientSession,
                                     frame: np.ndarray) -> Dict:
        """
        Met à jour la base de données des personnes reconnues.
        Utilise le tracker global pour éviter les reconnaissances répétées.
        """
        annotations = {}

        for info, results, embedding in zip(track_info, results_list, embeddings_list):
            track_id = info["track_id"]
            x, y, w, h = info["x"], info["y"], info["w"], info["h"]

            name = "Inconnu"
            recognition_score = 0.0
            color = self.config.COLOR_UNKNOWN
            person_id = None
            from_cache = False

            # ÉTAPE 1 : Vérifier le cache global AVANT l'API
            if self.global_tracker and embedding is not None:
                cached_match = self.global_tracker.find_person_by_embedding(embedding, self.cam_id)
                if cached_match:
                    name = cached_match["name"]
                    recognition_score = cached_match["score"]
                    print(f"✓ Cache global : {name} réidentifié(e) (person_id={cached_match['person_id']})")  # Debug console
                    person_id = cached_match["person_id"]
                    color = self.config.COLOR_RECOGNIZED
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

            if not from_cache and results and results[0].get("score", 0) > self.adaptive_threshold.value:
                name = results[0].get("name", "Inconnu")
                recognition_score = results[0].get("score", 0.0)

                color = self.config.COLOR_RECOGNIZED

                if self.global_tracker and embedding is not None:
                    person_id = self.global_tracker.find_or_register(
                        name=name,
                        embedding=embedding,
                        camera_id=self.cam_id,
                        track_id=track_id,
                        recognition_score=recognition_score
                    )

                try:
                    await send_event_async(
                        session, frame, self.cam_id,
                        person_id if person_id is not None else -1,
                        EVENTS[0], recognition_score
                    )
                except Exception as e:
                    logger.warning(f"Échec envoi événement pour person_id={person_id}: {e}")

            self.person_db[track_id] = {
                "name": name,
                "score": recognition_score,
                "last_updated": frame_idx,
                "person_id": person_id,
                "from_cache": from_cache
            }
            annotations[track_id] = {
                "bbox": (x, y, w, h),
                "name": name,
                "score": recognition_score,
                "color": color
            }

        return annotations

    async def _run_recognition_pipeline(self, recognition_tasks: List, track_info: List,
                                        embeddings_list: List, frame_idx: int,
                                        frame: np.ndarray) -> Dict:
        """
        Fix perf #2 : utilise self._session (persistante) au lieu d'ouvrir
        une nouvelle connexion TCP/TLS à chaque batch de reconnaissance.
        """
        results = await self.process_recognitions(recognition_tasks, self._session)
        return await self.update_person_database(
            track_info, results, frame_idx, embeddings_list, self._session, frame
        )

    def annotate_frame(self, frame: np.ndarray, track_id: int, bbox: Tuple,
                       name: str, score: float, color: Tuple) -> np.ndarray:
        """Dessine la box + étiquette avec fond sombre (style YOLO)."""
        x, y, w, h = bbox
        x2, y2 = x + w, y + h
        fh, fw = frame.shape[:2]

        cv2.rectangle(frame, (x, y), (x2, y2), color, 2)

        line1 = f"{name}  ID:{track_id}"
        line2 = f"Score: {score:.2f} ({score:.0%})" if score > 0 else ""

        font       = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.55
        thickness  = 1
        pad        = 4

        (tw1, th1), bl1 = cv2.getTextSize(line1, font, font_scale, thickness)
        (tw2, th2), _   = cv2.getTextSize(line2, font, font_scale, thickness) if line2 else ((0, 0), 0)

        label_w = max(tw1, tw2) + pad * 2
        label_h = th1 + (th2 + pad if line2 else 0) + pad * 2

        # Étiquette collée sous le bord supérieur de la box (à l'intérieur)
        lx1 = max(0, x)
        ly1 = max(0, y)
        lx2 = min(fw, lx1 + label_w)
        ly2 = min(fh, ly1 + label_h)

        # Fond semi-transparent
        overlay = frame.copy()
        cv2.rectangle(overlay, (lx1, ly1), (lx2, ly2), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.55, frame, 0.45, 0, frame)

        # Ligne 1 : nom + ID
        cv2.putText(frame, line1,
                    (lx1 + pad, ly1 + pad + th1),
                    font, font_scale, color, thickness, cv2.LINE_AA)

        # Ligne 2 : score (uniquement si > 0)
        if line2:
            cv2.putText(frame, line2,
                        (lx1 + pad, ly1 + pad + th1 + pad + th2),
                        font, font_scale, (255, 255, 255), thickness, cv2.LINE_AA)

        return frame

    def add_camera_overlay(self, frame: np.ndarray) -> np.ndarray:
        """Ajoute le titre de la caméra sur la frame"""
        overlay = f"{self.cam_name} (ID: {self.cam_id}) - {self.location}"
        cv2.putText(frame, overlay, (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, self.config.COLOR_TEXT_BG, 3, cv2.LINE_AA)
        cv2.putText(frame, overlay, (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, self.config.COLOR_TEXT_FG, 2, cv2.LINE_AA)
        return frame

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

    def _run_plate_detection(self, frame: np.ndarray, frame_to_display: np.ndarray,
                             frame_idx: int) -> np.ndarray:
        """Pipeline LPR complet sur une frame traitée (détection + OCR + annot.)."""
        if not self._lpr_enabled():
            return frame_to_display
        pp = self._ensure_plate_processor()
        if pp is None:
            return frame_to_display
        try:
            return pp.process(frame, frame_to_display, frame_idx, self.loop, self._session)
        except Exception as e:
            logger.error(f"[LPR][cam={self.cam_name}] erreur pipeline plaques : {e}")
            return frame_to_display

    def _redraw_plates(self, frame_to_display: np.ndarray) -> np.ndarray:
        """Redessine les boîtes plaques en cache sur une frame sautée."""
        if self._lpr_enabled() and self.plate_processor is not None:
            try:
                return self.plate_processor.annotate_cached(frame_to_display)
            except Exception:
                pass
        return frame_to_display

    def run(self):
        """Boucle principale de traitement"""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

        # Fix perf #2 : session HTTP ouverte une seule fois pour toute la durée du thread
        async def _open():
            return aiohttp.ClientSession()
        self._session = self.loop.run_until_complete(_open())

        try:
            while not self.stop_event.is_set():
                try:
                    frame = self.frame_queue.get(timeout=self.config.FRAME_QUEUE_TIMEOUT)
                except queue.Empty:
                    continue

                self.frame_counter += 1
                self.frame_idx_container[self.cam_id] += 1
                frame_idx = self.frame_idx_container[self.cam_id]

                if self.frame_counter % self.config.PROCESS_EVERY_N_FRAME == 0:
                    # Quality gate : rejeter les frames trop floues AVANT l'inférence GPU.
                    # Coût : ~0.3ms vs 15-30ms pour SCRFD — ratio bénéfice/coût très favorable.
                    # Un embedding extrait d'un frame flou dégrade cosine_sim de 0.05–0.20.
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
                            # Réutiliser les dernières annotations sans déclencher l'inférence
                            frame_to_display = frame.copy()
                            for track_id, bbox in self._last_bboxes.items():
                                if track_id in self.person_db:
                                    cached = self.person_db[track_id]
                                    color = (self.config.COLOR_RECOGNIZED if cached["name"] != "Inconnu"
                                             else self.config.COLOR_UNKNOWN)
                                    frame_to_display = self.annotate_frame(
                                        frame_to_display, track_id, bbox,
                                        cached["name"], cached["score"], color
                                    )
                                else:
                                    x, y, w, h = bbox
                                    cv2.rectangle(frame_to_display, (x, y), (x + w, y + h),
                                                  self.config.COLOR_UNKNOWN, 2)
                            frame_to_display = self._redraw_plates(frame_to_display)
                            frame_to_display = self.add_camera_overlay(frame_to_display)
                            with self.result_lock:
                                self.result_frames[self.cam_id] = frame_to_display
                            continue  # retour au début du while sans passer par le GPU

                    # Single GPU pass: SCRFD detection + alignment + ArcFace embedding
                    frame_annotated, faces_data = detect_faces_with_embeddings(
                        frame, confidence_threshold=self.config.FACE_DETECTION_CONFIDENCE
                    )

                    output_results, faces_indexed = self.prepare_detections(faces_data)
                    img_info = [frame.shape[0], frame.shape[1]]
                    img_size = [frame.shape[0], frame.shape[1]]

                    tracks = self.tracker.update(output_results, img_info, img_size)

                    # Fix 1 : mémoriser les positions de tous les tracks actifs
                    active_ids = {track.track_id for track in tracks}
                    for track in tracks:
                        tlwh = track.tlwh
                        self._last_bboxes[track.track_id] = (
                            int(tlwh[0]), int(tlwh[1]), int(tlwh[2]), int(tlwh[3])
                        )
                    for tid in list(self._last_bboxes):
                        if tid not in active_ids:
                            del self._last_bboxes[tid]

                    recognition_tasks = []
                    embeddings_list = []
                    track_info = []

                    # Embeddings already produced by the GPU detection pass — no extra inference step.
                    for track in tracks:
                        track_id = track.track_id
                        if self.should_recognize_track(track_id, frame_idx):
                            embedding, bbox = self.find_best_embedding_for_track(track, faces_indexed)
                            if embedding is not None:
                                recognition_tasks.append(embedding)
                                embeddings_list.append(embedding)
                                track_info.append({
                                    "track_id": track_id,
                                    "x": bbox[0], "y": bbox[1], "w": bbox[2], "h": bbox[3]
                                })

                    if recognition_tasks:
                        annotations = self.loop.run_until_complete(
                            self._run_recognition_pipeline(
                                recognition_tasks, track_info, embeddings_list, frame_idx, frame
                            )
                        )
                        for track_id, data in annotations.items():
                            frame_annotated = self.annotate_frame(
                                frame_annotated, track_id, data["bbox"],
                                data["name"], data["score"], data["color"]
                            )

                    # Annoter les tracks déjà en cache (pas re-soumis à l'API)
                    processed_track_ids = {t["track_id"] for t in track_info}
                    for track in tracks:
                        track_id = track.track_id
                        if track_id in self.person_db and track_id not in processed_track_ids:
                            tlwh = track.tlwh
                            x, y, w, h = int(tlwh[0]), int(tlwh[1]), int(tlwh[2]), int(tlwh[3])
                            cached = self.person_db[track_id]
                            name = cached["name"]
                            recognition_score = cached["score"]
                            color = (self.config.COLOR_RECOGNIZED if name != "Inconnu"
                                     else self.config.COLOR_UNKNOWN)
                            frame_annotated = self.annotate_frame(
                                frame_annotated, track_id, (x, y, w, h),
                                name, recognition_score, color
                            )

                    frame_to_display = frame_annotated
                    self.cleanup_cache(frame_idx)

                    # ── LPR : détection + lecture des plaques (parallèle au facial) ──
                    frame_to_display = self._run_plate_detection(frame, frame_to_display, frame_idx)

                else:
                    # Fix 1 : re-appliquer les dernières annotations connues
                    # Avant : frame brute sur 9/10 frames → boîtes clignotantes à 3 Hz
                    # Après : annotations stables à 30 FPS, positions figées entre détections
                    frame_to_display = frame.copy()
                    for track_id, bbox in self._last_bboxes.items():
                        if track_id in self.person_db:
                            cached = self.person_db[track_id]
                            color = (self.config.COLOR_RECOGNIZED if cached["name"] != "Inconnu"
                                     else self.config.COLOR_UNKNOWN)
                            frame_to_display = self.annotate_frame(
                                frame_to_display, track_id, bbox,
                                cached["name"], cached["score"], color
                            )
                        else:
                            x, y, w, h = bbox
                            cv2.rectangle(frame_to_display, (x, y), (x + w, y + h),
                                          self.config.COLOR_UNKNOWN, 2)

                    frame_to_display = self._redraw_plates(frame_to_display)

                frame_to_display = self.add_camera_overlay(frame_to_display)
                with self.result_lock:
                    self.result_frames[self.cam_id] = frame_to_display

        finally:
            # Arrêt propre du worker réseau LPR (thread + session aiohttp dédiés).
            if self.plate_processor is not None:
                try:
                    self.plate_processor.shutdown()
                except Exception as e:
                    logger.debug(f"[LPR][cam={self.cam_name}] arrêt worker LPR : {e}")
            async def _close():
                if self._session and not self._session.closed:
                    await self._session.close()
            self.loop.run_until_complete(_close())
            self.loop.close()

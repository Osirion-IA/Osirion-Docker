# core/tracking_processor.py
"""
Vision Engine — détection de personnes (ANONYME) + tracking, pour UNE caméra.

Responsabilité UNIQUE : produire le « Scene Model » de chaque frame traitée —
des personnes anonymes (track_id persistant, bbox, point au sol, vitesse) — SANS
aucune identité ni logique métier. Le Scene Model est publié en JSON via
Socket.IO ('metadata') ; la vidéo est servie séparément par MediaMTX (WebRTC).

C'est la SEULE couche GPU : une passe YOLO par frame traitée (person_detection).
Tout traitement en aval (zones, comptage, files, règles) se fait côté CPU à
partir de ce Scene Model, hors du chemin critique vidéo.
"""
import cv2
import numpy as np
import time
from collections import deque
from typing import Dict, List, Optional
import queue
import threading

from person_detection import detect_persons
from utils.logger import get_logger
from utils.monitoring import emit_blur_metric
from utils.measurement import get_measurement

logger = get_logger(__name__)


class TrackingProcessor:
    """Détection de personnes + tracking pour une caméra (Scene Model anonyme)."""

    def __init__(self, cam: Dict, frame_queue: queue.Queue, result_frames: Dict,
                 result_lock, tracker, frame_idx_container: Dict,
                 stop_event, config, result_metadata: Dict = None):
        self.cam_id = cam["id"]
        self.cam_name = cam["cam_name"]
        self.location = cam.get("location")
        self.frame_queue = frame_queue
        self.result_frames = result_frames
        # On ne dessine plus sur la frame : on publie un Scene Model JSON dans
        # result_metadata[cam_id] ; le serveur web le diffuse en 'metadata'.
        self.result_metadata = result_metadata if result_metadata is not None else {}
        self.result_lock = result_lock
        self.tracker = tracker
        self.frame_idx_container = frame_idx_container
        self.stop_event = stop_event
        self.config = config

        self.frame_counter = 0
        self._blur_skip_count = 0
        # Dernier point au sol par track → dérive vitesse/direction (Scene Model).
        self._last_foot: Dict[int, tuple] = {}

        # ── Mesure (chapitre 4) : latence par frame TRAITÉE ──────────────────
        # detect_ms = coût de la passe YOLO (GPU) ; frame_ms = coût total (détection
        # + tracking + construction JSON). Accumulateurs vidés par le sampler.
        self.measure = get_measurement()
        self._lat_lock = threading.Lock()
        self._detect_ms: deque = deque(maxlen=4000)
        self._frame_ms: deque = deque(maxlen=4000)

    # ──────────────────────────────────────────────────────────────────────
    # Qualité d'image
    # ──────────────────────────────────────────────────────────────────────
    @staticmethod
    def _compute_frame_sharpness(frame: np.ndarray) -> float:
        """Netteté de la frame (variance du Laplacien) — gate anti-flou."""
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame
        return float(cv2.Laplacian(gray, cv2.CV_64F).var())

    # ──────────────────────────────────────────────────────────────────────
    # Mesure de latence (alimentée par run(), lue par le sampler système)
    # ──────────────────────────────────────────────────────────────────────
    def _record_latency(self, detect_ms: Optional[float],
                        frame_ms: Optional[float] = None) -> None:
        with self._lat_lock:
            if detect_ms is not None:
                self._detect_ms.append(detect_ms)
            if frame_ms is not None:
                self._frame_ms.append(frame_ms)

    def latency_snapshot(self, reset: bool = True) -> Dict:
        """Instantané des latences depuis le dernier appel (fenêtre non chevauchante).
        Le sampler en déduit aussi le débit réel (n_detections / durée d'intervalle)."""
        with self._lat_lock:
            detect = list(self._detect_ms)
            frame = list(self._frame_ms)
            if reset:
                self._detect_ms.clear()
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
            "n_detections": len(detect),
            "n_frame": len(frame),
            "detect_ms": _stats(detect),
            "frame_ms": _stats(frame),
        }

    # ──────────────────────────────────────────────────────────────────────
    # Adaptation vers l'entrée OC-SORT
    # ──────────────────────────────────────────────────────────────────────
    @staticmethod
    def _to_output_results(boxes: List) -> np.ndarray:
        """[[x1,y1,x2,y2,score], …] → ndarray Nx5 attendu par l'adaptateur OC-SORT."""
        if not boxes:
            return np.empty((0, 5), dtype=float)
        return np.asarray(boxes, dtype=float)

    # ──────────────────────────────────────────────────────────────────────
    # Boucle principale
    # ──────────────────────────────────────────────────────────────────────
    def run(self):
        logger.info(f"[cam={self.cam_name}] traitement démarré (détection de personnes).")
        blur_threshold = getattr(self.config, "BLUR_THRESHOLD", 0.0) or 0.0
        conf = getattr(self.config, "PERSON_DETECTION_CONFIDENCE", 0.4)
        try:
            while not self.stop_event.is_set():
                try:
                    frame = self.frame_queue.get(timeout=self.config.FRAME_QUEUE_TIMEOUT)
                except queue.Empty:
                    continue

                self.frame_counter += 1
                frame_idx = self.frame_counter
                self.frame_idx_container[self.cam_id] = frame_idx

                detections: List[Dict] = []
                detect_ms: Optional[float] = None
                _t_frame = time.perf_counter()

                # ── Gate anti-flou (frame entière) : on saute l'inférence sur une
                #    frame trop floue ; l'overlay précédent reste affiché. ─────────
                skip = False
                if blur_threshold > 0:
                    sharpness = self._compute_frame_sharpness(frame)
                    if sharpness < blur_threshold:
                        self._blur_skip_count += 1
                        if self._blur_skip_count % 30 == 1:
                            emit_blur_metric(
                                camera_id=self.cam_id, camera_name=self.cam_name,
                                sharpness=sharpness, threshold=blur_threshold,
                                total_skipped=self._blur_skip_count,
                            )
                        skip = True

                if not skip:
                    # ── Détection de personnes (unique passe GPU) ────────────────
                    _t = time.perf_counter()
                    boxes = detect_persons(frame, confidence_threshold=conf)
                    detect_ms = (time.perf_counter() - _t) * 1000.0

                    # ── Tracking (OC-SORT) → identifiants anonymes persistants ───
                    img_info = [frame.shape[0], frame.shape[1]]
                    tracks = self.tracker.update(
                        self._to_output_results(boxes), img_info, img_info
                    )

                    for track in tracks:
                        tlwh = track.tlwh
                        x, y, w, h = int(tlwh[0]), int(tlwh[1]), int(tlwh[2]), int(tlwh[3])
                        tid = int(track.track_id)
                        # Point au sol = centre du bord inférieur (projection « pieds »).
                        foot = (x + w / 2.0, y + h)
                        prev = self._last_foot.get(tid)
                        vx, vy = (foot[0] - prev[0], foot[1] - prev[1]) if prev else (0.0, 0.0)
                        self._last_foot[tid] = foot
                        detections.append({
                            "type": "person",
                            "track_id": tid,
                            "bbox": [x, y, x + w, y + h],
                            "foot": [round(foot[0], 1), round(foot[1], 1)],
                            "velocity": [round(vx, 1), round(vy, 1)],
                        })

                    # Purge périodique de l'historique des tracks disparus (mémoire).
                    if self.frame_counter % 300 == 0 and self._last_foot:
                        live = {int(t.track_id) for t in tracks}
                        self._last_foot = {k: v for k, v in self._last_foot.items() if k in live}

                frame_ms = (time.perf_counter() - _t_frame) * 1000.0
                self._record_latency(detect_ms, frame_ms)

                # ── Publication du Scene Model (overlay frontend) ────────────────
                # bbox dans le repère de la frame traitée (width×height) ; le
                # frontend les met à l'échelle vers la taille d'affichage réelle.
                fh, fw = frame.shape[:2]
                payload = {
                    "camera_id": self.cam_id,
                    "width": fw,
                    "height": fh,
                    "detections": detections,
                }
                with self.result_lock:
                    self.result_metadata[self.cam_id] = {"seq": frame_idx, "payload": payload}

        except Exception:
            logger.error(f"[cam={self.cam_name}] erreur fatale du traitement", exc_info=True)
        finally:
            logger.info(f"[cam={self.cam_name}] traitement arrêté.")

# core/plate_processor.py
"""
Traitement LPR/ANPR par caméra : détection plaque → tracking parallèle →
OCR avec frame-skipping (cache par track_id) → recherche floue backend →
événement → annotation.

Conçu pour tourner EN PARALLÈLE du pipeline facial (TrackingProcessor) sur la
même frame, sans jamais le perturber : si le module LPR est indisponible
(plate_detection.LPR_AVAILABLE == False), process() est un quasi no-op.

Optimisation clé (frame-skipping OCR) :
  - L'OCR n'est lancé que tant qu'un track n'a pas de lecture "définitive"
    (confiance ≥ PLATE_OCR_GOOD_CONFIDENCE) et sous PLATE_OCR_MAX_ATTEMPTS.
  - Une fois la plaque lue avec confiance, le texte est MIS EN CACHE pour ce
    track_id et l'OCR est COMPLÈTEMENT SAUTÉ sur les frames suivantes.
"""
import cv2
import numpy as np
from typing import Dict, List, Optional

from ByteTrack.yolox.tracker.byte_tracker import BYTETracker
import plate_detection
from plate_detection import detect_plates, read_plate_text
from services.plate_search_service import search_plate_async
from services.event_services import send_plate_event_async
from utils.logger import get_logger

logger = get_logger(__name__)


class PlateProcessor:
    """Gère la détection + lecture des plaques pour UNE caméra."""

    def __init__(self, cam: Dict, config):
        self.cam_id = cam["id"]
        self.cam_name = cam["cam_name"]
        self.config = config

        # Tracker ByteTrack dédié aux plaques (parallèle à celui des visages).
        self.tracker = BYTETracker(
            config.BYTE_TRACK_ARGS, frame_rate=config.BYTE_TRACK_FRAME_RATE
        )

        # Cache par track_id : { plate_text, ocr_conf, attempts, finalized,
        #   bbox, vehicle_id, is_blacklisted, owner_name, looked_up_for,
        #   event_sent, last_updated }
        self.plate_db: Dict[int, Dict] = {}

        self.det_conf = getattr(config, 'PLATE_DETECTION_CONFIDENCE', 0.45)
        self.ocr_min = getattr(config, 'PLATE_OCR_MIN_CONFIDENCE', 0.40)
        self.ocr_good = getattr(config, 'PLATE_OCR_GOOD_CONFIDENCE', 0.65)
        self.max_attempts = getattr(config, 'PLATE_OCR_MAX_ATTEMPTS', 5)
        self.search_threshold = getattr(config, 'PLATE_SEARCH_THRESHOLD', 0.82)
        self.ttl_frames = getattr(config, 'PLATE_CACHE_TTL_FRAMES', 600)

        self.color_plate = getattr(config, 'COLOR_PLATE', (0, 200, 255))
        self.color_black = getattr(config, 'COLOR_PLATE_BLACKLIST', (0, 0, 255))
        self.color_known = getattr(config, 'COLOR_PLATE_KNOWN', (255, 200, 0))

        # Tracks actifs lors de la dernière frame traitée (pour redessiner les
        # boîtes plaques sur les frames sautées, sans relancer la détection).
        self._active_ids: set = set()

    # ──────────────────────────────────────────────────────────────────────
    # Entrée principale (appelée par TrackingProcessor sur les frames traitées)
    # ──────────────────────────────────────────────────────────────────────
    def process(self, frame: np.ndarray, frame_annotated: np.ndarray,
                frame_idx: int, loop, session) -> np.ndarray:
        """
        Détecte/lit les plaques sur `frame`, annote `frame_annotated` et renvoie
        ce dernier. `loop`/`session` = boucle asyncio + session aiohttp du
        TrackingProcessor (réutilisées pour les appels réseau).
        """
        if not plate_detection.LPR_AVAILABLE:
            return frame_annotated

        detections = detect_plates(frame, confidence_threshold=self.det_conf)

        # Préparer pour ByteTrack : (N,5) [x1,y1,x2,y2,score]
        if detections:
            dets = np.array(
                [[x, y, x + w, y + h, conf] for (x, y, w, h), conf in detections],
                dtype=np.float32,
            )
        else:
            dets = np.empty((0, 5), dtype=np.float32)

        img_info = [frame.shape[0], frame.shape[1]]
        tracks = self.tracker.update(dets, img_info, img_info)

        fh, fw = frame.shape[:2]
        pending_lookup: List[int] = []
        self._active_ids = {track.track_id for track in tracks}

        for track in tracks:
            tid = track.track_id
            tlwh = track.tlwh
            x, y, w, h = int(tlwh[0]), int(tlwh[1]), int(tlwh[2]), int(tlwh[3])
            x, y = max(0, x), max(0, y)
            w, h = max(1, min(w, fw - x)), max(1, min(h, fh - y))

            entry = self.plate_db.get(tid)
            if entry is None:
                entry = {
                    "plate_text": "", "ocr_conf": 0.0, "attempts": 0,
                    "finalized": False, "bbox": (x, y, w, h),
                    "vehicle_id": None, "is_blacklisted": False, "owner_name": None,
                    "looked_up_for": None, "event_sent": False, "last_updated": frame_idx,
                }
                self.plate_db[tid] = entry
            entry["bbox"] = (x, y, w, h)
            entry["last_updated"] = frame_idx

            # ── Frame-skipping OCR : OCR seulement si pas encore "définitif" ──
            if not entry["finalized"] and entry["attempts"] < self.max_attempts:
                crop = frame[y:y + h, x:x + w]
                text, conf = read_plate_text(crop)
                entry["attempts"] += 1
                if text and conf >= self.ocr_min and conf > entry["ocr_conf"]:
                    entry["plate_text"] = text
                    entry["ocr_conf"] = conf
                    if conf >= self.ocr_good:
                        entry["finalized"] = True
            # else : lecture déjà figée → OCR SAUTÉ, on réutilise le cache

            # Programmer une recherche backend si nouveau texte non encore résolu
            if entry["plate_text"] and entry["looked_up_for"] != entry["plate_text"]:
                pending_lookup.append(tid)

        # ── Résolution réseau (recherche floue + événement) en asynchrone ──
        if pending_lookup:
            try:
                loop.run_until_complete(self._resolve(pending_lookup, frame, session))
            except Exception as e:
                logger.error(f"[LPR][cam={self.cam_name}] résolution réseau échouée : {e}")

        # ── Annotation (tracks actifs de cette frame) ──
        for tid in self._active_ids:
            entry = self.plate_db.get(tid)
            if entry:
                self._annotate(frame_annotated, entry)

        self._cleanup(frame_idx)
        return frame_annotated

    def annotate_cached(self, frame: np.ndarray) -> np.ndarray:
        """Redessine les boîtes plaques des derniers tracks actifs (frames sautées,
        sans relancer détection/OCR). Garde l'affichage stable entre 2 détections."""
        if not plate_detection.LPR_AVAILABLE:
            return frame
        for tid in self._active_ids:
            entry = self.plate_db.get(tid)
            if entry:
                self._annotate(frame, entry)
        return frame

    # ──────────────────────────────────────────────────────────────────────
    async def _resolve(self, track_ids: List[int], frame: np.ndarray, session):
        """Recherche floue backend + envoi d'événement (1 fois par track)."""
        for tid in track_ids:
            entry = self.plate_db.get(tid)
            if not entry or not entry["plate_text"]:
                continue

            match = await search_plate_async(
                session, entry["plate_text"], threshold=self.search_threshold, k=1
            )
            entry["looked_up_for"] = entry["plate_text"]
            if match:
                entry["vehicle_id"] = match.get("id")
                entry["is_blacklisted"] = bool(match.get("is_blacklisted"))
                entry["owner_name"] = match.get("owner_name")
                logger.info(
                    f"[LPR][cam={self.cam_name}] plaque {entry['plate_text']} → "
                    f"connue (vehicle_id={entry['vehicle_id']}, "
                    f"blacklist={entry['is_blacklisted']}, score={match.get('score')})"
                )
                if entry["is_blacklisted"]:
                    logger.warning(
                        f"🚨 [ALERTE BLACKLIST] Plaque {entry['plate_text']} détectée "
                        f"sur caméra {self.cam_name} (vehicle_id={entry['vehicle_id']})"
                    )
            else:
                logger.info(
                    f"[LPR][cam={self.cam_name}] plaque {entry['plate_text']} → inconnue"
                )

            # Événement : une seule fois par track, dès la 1re identification confiante
            if not entry["event_sent"]:
                try:
                    await send_plate_event_async(
                        session, frame, self.cam_id,
                        entry["plate_text"], entry["ocr_conf"],
                        vehicle_id=entry["vehicle_id"],
                    )
                    entry["event_sent"] = True
                except Exception as e:
                    logger.warning(f"[LPR] échec envoi événement plaque {entry['plate_text']}: {e}")

    # ──────────────────────────────────────────────────────────────────────
    def _annotate(self, frame: np.ndarray, entry: Dict) -> None:
        x, y, w, h = entry["bbox"]
        if entry["is_blacklisted"]:
            color = self.color_black
        elif entry["vehicle_id"] is not None:
            color = self.color_known
        else:
            color = self.color_plate

        cv2.rectangle(frame, (x, y), (x + w, y + h), color, 2)

        text = entry["plate_text"] or "..."
        label = text
        if entry["is_blacklisted"]:
            label = f"{text} [BLACKLIST]"
        elif entry["owner_name"]:
            label = f"{text} ({entry['owner_name']})"

        font, scale, thick = cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2
        (tw, th), bl = cv2.getTextSize(label, font, scale, thick)
        ly = max(0, y - th - 8)
        cv2.rectangle(frame, (x, ly), (x + tw + 8, ly + th + bl + 6), color, -1)
        cv2.putText(frame, label, (x + 4, ly + th + 2), font, scale, (0, 0, 0), thick, cv2.LINE_AA)

    def _cleanup(self, frame_idx: int) -> None:
        expired = [tid for tid, e in self.plate_db.items()
                   if frame_idx - e["last_updated"] > self.ttl_frames]
        for tid in expired:
            del self.plate_db[tid]

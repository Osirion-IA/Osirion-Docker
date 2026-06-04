# core/plate_processor.py
"""
Traitement LPR/ANPR par caméra : détection plaque → tracking parallèle →
OCR avec frame-skipping (cache par track_id) → recherche floue backend →
événement → annotation.

Conçu pour tourner EN PARALLÈLE du pipeline facial (TrackingProcessor) sur la
même frame, sans jamais le perturber : si le module LPR est indisponible
(plate_detection.LPR_AVAILABLE == False), process() est un quasi no-op.

Optimisations (cf. config.settings, section « OPTIMISATIONS latence & précision ») :

  • LATENCE — résolution réseau DÉCOUPLÉE : la recherche floue + l'envoi
    d'événement partent dans un thread worker dédié (file FIFO). Le thread
    caméra n'est JAMAIS bloqué par le réseau (avant : loop.run_until_complete
    bloquant pouvait figer le flux plusieurs secondes si le backend ramait).

  • LATENCE — cadence de détection : YOLO ne tourne qu'1 frame traitée sur
    PLATE_PROCESS_EVERY_N (le cache OCR couvre les frames intermédiaires).

  • LATENCE/PRÉCISION — gating : on n'OCR pas les crops trop petits ou (option)
    trop flous → moins de calcul gaspillé, moins de lectures poubelle.

  • PRÉCISION — VOTE TEMPOREL : au lieu de figer la 1re lecture haute-confiance,
    on accumule les lectures OCR le long du track et on vote caractère par
    caractère (robuste aux flous/reflets ponctuels).

  • PRÉCISION — validation par format (regex) OPTIONNELLE : une lecture
    hors-format n'est jamais recherchée (réduit les faux positifs blacklist).

Frame-skipping OCR conservé : une fois la plaque « définitive », le texte est
mis en cache pour ce track_id et l'OCR est COMPLÈTEMENT sauté ensuite.
"""
import queue
import re
import threading
from collections import defaultdict
from typing import Dict, List, Optional

import asyncio
import aiohttp
import cv2
import numpy as np

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

        # Cache par track_id. Champs : plate_text, ocr_conf, attempts, finalized,
        #   bbox, readings[], vehicle_id, is_blacklisted, owner_name,
        #   looked_up_for, lookup_inflight, event_sent, last_updated.
        self.plate_db: Dict[int, Dict] = {}

        self.det_conf = getattr(config, 'PLATE_DETECTION_CONFIDENCE', 0.45)
        self.ocr_min = getattr(config, 'PLATE_OCR_MIN_CONFIDENCE', 0.40)
        self.ocr_good = getattr(config, 'PLATE_OCR_GOOD_CONFIDENCE', 0.65)
        self.max_attempts = getattr(config, 'PLATE_OCR_MAX_ATTEMPTS', 5)
        self.search_threshold = getattr(config, 'PLATE_SEARCH_THRESHOLD', 0.82)
        self.ttl_frames = getattr(config, 'PLATE_CACHE_TTL_FRAMES', 600)

        # ── Optimisations ────────────────────────────────────────────────────
        self.process_every_n = max(1, getattr(config, 'PLATE_PROCESS_EVERY_N', 1))
        self.min_crop_w = getattr(config, 'PLATE_MIN_CROP_WIDTH', 0)
        self.min_crop_h = getattr(config, 'PLATE_MIN_CROP_HEIGHT', 0)
        self.crop_min_sharp = getattr(config, 'PLATE_CROP_MIN_SHARPNESS', 0.0)
        self.voting = getattr(config, 'PLATE_TEMPORAL_VOTING', True)
        self.vote_min_agree = max(1, getattr(config, 'PLATE_VOTE_MIN_AGREE', 2))

        fmt = getattr(config, 'PLATE_FORMAT_REGEX', '') or ''
        try:
            self._format_re = re.compile(fmt) if fmt else None
        except re.error as e:
            logger.warning(f"[LPR] PLATE_FORMAT_REGEX invalide ({e}) — ignoré.")
            self._format_re = None

        self.color_plate = getattr(config, 'COLOR_PLATE', (0, 200, 255))
        self.color_black = getattr(config, 'COLOR_PLATE_BLACKLIST', (0, 0, 255))
        self.color_known = getattr(config, 'COLOR_PLATE_KNOWN', (255, 200, 0))

        # Tracks actifs lors de la dernière frame de DÉTECTION (pour redessiner
        # les boîtes plaques sur les frames sautées, sans relancer la détection).
        self._active_ids: set = set()
        self._proc_count = 0   # compteur interne pour la cadence de détection

        # ── Worker réseau découplé ────────────────────────────────────────────
        # Le thread caméra ne fait QUE détecter/lire/annoter. La recherche floue
        # et l'envoi d'événement (lents, réseau) sont délégués à ce worker.
        maxq = getattr(config, 'PLATE_LOOKUP_QUEUE_MAXSIZE', 64)
        self._jobs: "queue.Queue" = queue.Queue(maxsize=maxq)
        self._results: "queue.Queue" = queue.Queue()
        self._stop = threading.Event()
        self._worker = threading.Thread(
            target=self._lookup_loop, name=f"lpr-lookup-{self.cam_id}", daemon=True
        )
        self._worker.start()

    # ──────────────────────────────────────────────────────────────────────
    # Entrée principale (appelée par TrackingProcessor sur les frames traitées)
    # ──────────────────────────────────────────────────────────────────────
    def process(self, frame: np.ndarray, frame_annotated: np.ndarray,
                frame_idx: int, loop=None, session=None) -> np.ndarray:
        """
        Détecte/lit les plaques sur `frame`, annote `frame_annotated` et renvoie
        ce dernier. `loop`/`session` sont acceptés pour compatibilité mais ne
        sont plus utilisés (le worker réseau interne gère les appels).
        """
        if not plate_detection.LPR_AVAILABLE:
            return frame_annotated

        # 1) Appliquer les résultats réseau revenus du worker (non bloquant).
        self._drain_results()

        # 2) Cadence : ne lancer la détection YOLO qu'1 frame sur N.
        self._proc_count += 1
        if self._proc_count % self.process_every_n != 0:
            return self.annotate_cached(frame_annotated)

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
        self._active_ids = {track.track_id for track in tracks}

        for track in tracks:
            tid = track.track_id
            tlwh = track.tlwh
            x, y, w, h = int(tlwh[0]), int(tlwh[1]), int(tlwh[2]), int(tlwh[3])
            x, y = max(0, x), max(0, y)
            w, h = max(1, min(w, fw - x)), max(1, min(h, fh - y))

            entry = self.plate_db.get(tid)
            if entry is None:
                entry = self._new_entry(x, y, w, h, frame_idx)
                self.plate_db[tid] = entry
            entry["bbox"] = (x, y, w, h)
            entry["last_updated"] = frame_idx

            # ── Frame-skipping OCR : OCR seulement si pas encore « définitif » ──
            if not entry["finalized"] and entry["attempts"] < self.max_attempts:
                self._try_read(entry, frame, x, y, w, h)

            # Programmer la résolution réseau dès que la lecture est définitive.
            if entry["finalized"] and entry["plate_text"]:
                self._schedule_lookup(tid, entry, frame)

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

    def shutdown(self) -> None:
        """Arrête proprement le worker réseau (appelé à l'arrêt de la caméra)."""
        self._stop.set()
        try:
            self._jobs.put_nowait(None)   # réveille le worker s'il attend
        except Exception:
            pass
        if self._worker is not None and self._worker.is_alive():
            self._worker.join(timeout=3)

    # ──────────────────────────────────────────────────────────────────────
    # Lecture OCR + vote temporel
    # ──────────────────────────────────────────────────────────────────────
    def _try_read(self, entry: Dict, frame: np.ndarray,
                  x: int, y: int, w: int, h: int) -> None:
        """OCR d'un crop avec gating (taille/netteté) puis agrégation (vote)."""
        # Gating taille : on ignore les plaques trop petites (illisibles).
        if w < self.min_crop_w or h < self.min_crop_h:
            return

        crop = frame[y:y + h, x:x + w]
        if crop is None or crop.size == 0:
            return

        # Gating netteté (optionnel) : on ne consomme pas une tentative sur un
        # crop flou — on attend une meilleure frame.
        if self.crop_min_sharp > 0.0 and self._sharpness(crop) < self.crop_min_sharp:
            return

        text, conf = read_plate_text(crop)
        entry["attempts"] += 1

        if text and conf >= self.ocr_min:
            if self.voting:
                entry["readings"].append((text, conf))
                cons_text, cons_conf = self._vote(entry["readings"])
                entry["plate_text"] = cons_text
                entry["ocr_conf"] = cons_conf
                agree = sum(1 for t, _ in entry["readings"] if t == cons_text)
                if (agree >= self.vote_min_agree and cons_conf >= self.ocr_good
                        and self._format_ok(cons_text)):
                    entry["finalized"] = True
            else:
                # Ancien comportement : meilleure lecture unique.
                if conf > entry["ocr_conf"]:
                    entry["plate_text"] = text
                    entry["ocr_conf"] = conf
                    if conf >= self.ocr_good and self._format_ok(text):
                        entry["finalized"] = True

        # Plus de tentatives possibles → on fige avec le meilleur consensus connu.
        if not entry["finalized"] and entry["attempts"] >= self.max_attempts:
            entry["finalized"] = True

    @staticmethod
    def _vote(readings: List) -> tuple:
        """Vote majoritaire caractère par caractère, pondéré par la confiance.

        1) longueur la plus représentée (compte, puis confiance cumulée),
        2) pour chaque position, caractère au score de confiance cumulé maximal.
        """
        if not readings:
            return "", 0.0
        by_len_count: Dict[int, float] = defaultdict(float)
        by_len_conf: Dict[int, float] = defaultdict(float)
        for t, c in readings:
            by_len_count[len(t)] += 1.0
            by_len_conf[len(t)] += c
        target_len = max(by_len_count.keys(),
                         key=lambda L: (by_len_count[L], by_len_conf[L]))
        same = [(t, c) for (t, c) in readings if len(t) == target_len]
        chars = []
        for i in range(target_len):
            score: Dict[str, float] = defaultdict(float)
            for t, c in same:
                score[t[i]] += c
            chars.append(max(score.items(), key=lambda kv: kv[1])[0])
        text = "".join(chars)
        conf = float(np.mean([c for _, c in same])) if same else 0.0
        return text, conf

    def _format_ok(self, text: str) -> bool:
        """True si pas de regex de format, ou si le texte la respecte."""
        if self._format_re is None:
            return True
        return bool(self._format_re.match(text))

    @staticmethod
    def _sharpness(crop: np.ndarray) -> float:
        """Variance du Laplacien (mesure de netteté). Best-effort."""
        try:
            gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3 else crop
            return float(cv2.Laplacian(gray, cv2.CV_64F).var())
        except Exception:
            return 1e9   # en cas d'erreur, ne bloque pas l'OCR

    def _new_entry(self, x: int, y: int, w: int, h: int, frame_idx: int) -> Dict:
        return {
            "plate_text": "", "ocr_conf": 0.0, "attempts": 0,
            "finalized": False, "bbox": (x, y, w, h), "readings": [],
            "vehicle_id": None, "is_blacklisted": False, "owner_name": None,
            "looked_up_for": None, "lookup_inflight": None,
            "event_sent": False, "last_updated": frame_idx,
        }

    # ──────────────────────────────────────────────────────────────────────
    # Résolution réseau DÉCOUPLÉE (worker thread + file FIFO)
    # ──────────────────────────────────────────────────────────────────────
    def _schedule_lookup(self, tid: int, entry: Dict, frame: np.ndarray) -> None:
        """Met en file une recherche floue (+ événement) pour ce track, sans bloquer."""
        text = entry["plate_text"]
        if not text:
            return
        # Déjà résolu ou en cours pour ce texte → rien à faire.
        if entry["looked_up_for"] == text or entry["lookup_inflight"] == text:
            return
        # Validation de format : on ne recherche pas les plaques hors-format
        # (évite des appariements/alertes erronés). On marque comme « traité ».
        if not self._format_ok(text):
            entry["looked_up_for"] = text
            return

        job = {
            "track_id": tid,
            "plate_text": text,
            "ocr_conf": entry["ocr_conf"],
            "frame": frame.copy(),               # snapshot pour l'événement
            "need_event": not entry["event_sent"],
        }
        try:
            self._jobs.put_nowait(job)
            entry["lookup_inflight"] = text
        except queue.Full:
            logger.warning(
                f"[LPR][cam={self.cam_name}] file de résolution pleine — "
                f"plaque {text} ignorée ce cycle (réessai au prochain)."
            )

    def _drain_results(self) -> None:
        """Applique (thread caméra) les résultats produits par le worker."""
        while True:
            try:
                r = self._results.get_nowait()
            except queue.Empty:
                break
            entry = self.plate_db.get(r["track_id"])
            if entry is None:
                continue
            # N'appliquer que si le texte du track n'a pas changé entre-temps.
            if entry["plate_text"] != r["plate_text"]:
                continue
            entry["vehicle_id"] = r["vehicle_id"]
            entry["is_blacklisted"] = r["is_blacklisted"]
            entry["owner_name"] = r["owner_name"]
            entry["looked_up_for"] = r["plate_text"]
            entry["lookup_inflight"] = None
            if r["event_sent"]:
                entry["event_sent"] = True

    def _lookup_loop(self) -> None:
        """Boucle du worker : possède sa propre boucle asyncio + session aiohttp."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        session = None
        try:
            session = loop.run_until_complete(self._mk_session())
            while not self._stop.is_set():
                try:
                    job = self._jobs.get(timeout=0.5)
                except queue.Empty:
                    continue
                if job is None:
                    break
                try:
                    loop.run_until_complete(self._handle_job(job, session))
                except Exception as e:
                    logger.error(
                        f"[LPR][cam={self.cam_name}] worker résolution : {e}"
                    )
        except Exception as e:
            logger.error(f"[LPR][cam={self.cam_name}] worker LPR arrêté : {e}")
        finally:
            try:
                if session is not None:
                    loop.run_until_complete(session.close())
            except Exception:
                pass
            loop.close()

    @staticmethod
    async def _mk_session() -> aiohttp.ClientSession:
        return aiohttp.ClientSession()

    async def _handle_job(self, job: Dict, session: aiohttp.ClientSession) -> None:
        """Recherche floue backend + envoi d'événement (1 fois par job)."""
        plate_text = job["plate_text"]
        result = {
            "track_id": job["track_id"], "plate_text": plate_text,
            "vehicle_id": None, "is_blacklisted": False,
            "owner_name": None, "event_sent": False,
        }

        match = await search_plate_async(
            session, plate_text, threshold=self.search_threshold, k=1
        )
        if match:
            result["vehicle_id"] = match.get("id")
            result["is_blacklisted"] = bool(match.get("is_blacklisted"))
            result["owner_name"] = match.get("owner_name")
            logger.info(
                f"[LPR][cam={self.cam_name}] plaque {plate_text} → connue "
                f"(vehicle_id={result['vehicle_id']}, "
                f"blacklist={result['is_blacklisted']}, score={match.get('score')})"
            )
            if result["is_blacklisted"]:
                logger.warning(
                    f"🚨 [ALERTE BLACKLIST] Plaque {plate_text} détectée sur "
                    f"caméra {self.cam_name} (vehicle_id={result['vehicle_id']})"
                )
        else:
            logger.info(f"[LPR][cam={self.cam_name}] plaque {plate_text} → inconnue")

        if job.get("need_event"):
            try:
                await send_plate_event_async(
                    session, job["frame"], self.cam_id,
                    plate_text, job["ocr_conf"], vehicle_id=result["vehicle_id"],
                )
                result["event_sent"] = True
            except Exception as e:
                logger.warning(f"[LPR] échec envoi événement plaque {plate_text}: {e}")

        self._results.put(result)

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

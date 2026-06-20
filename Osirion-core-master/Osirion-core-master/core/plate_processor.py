# core/plate_processor.py
"""
Traitement LPR/ANPR par caméra : détection plaque → tracking parallèle →
OCR avec frame-skipping (cache par track_id) → recherche floue backend →
événement → annotation.

Conçu pour tourner EN PARALLÈLE du pipeline facial (TrackingProcessor) sur la
même frame, sans jamais le perturber : si le module LPR est indisponible
(plate_detection.LPR_AVAILABLE == False), process() est un quasi no-op.

Optimisations (cf. config.settings, section « OPTIMISATIONS latence & précision ») :

  • LATENCE — OCR DÉCOUPLÉ : la lecture EasyOCR + l'ordre de lecture spatial 2D
    (filtrage hauteur, regroupement multi-lignes, validation) tournent dans un
    thread worker OCR dédié (file FIFO). Le thread caméra ne fait QUE détecter +
    tracker (YOLO/ByteTrack) et soumettre des crops : il n'est JAMAIS bloqué par
    l'OCR → aucune saccade sur la boucle de tracking vidéo WebRTC (avant : EasyOCR
    s'exécutait en ligne dans process() et pouvait figer le flux plusieurs ms/frame).

  • LATENCE — résolution réseau DÉCOUPLÉE : la recherche floue + l'envoi
    d'événement partent dans un SECOND thread worker dédié (file FIFO). Le thread
    caméra n'est JAMAIS bloqué par le réseau (avant : loop.run_until_complete
    bloquant pouvait figer le flux plusieurs secondes si le backend ramait).
    OCR (CPU/GPU) et réseau (asyncio) vivent dans deux workers séparés pour ne
    jamais se sérialiser l'un derrière l'autre.

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
import time
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
from utils.measurement import get_measurement

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
        #   bbox, readings[], ocr_inflight, vehicle_id, is_blacklisted, owner_name,
        #   looked_up_for, lookup_inflight, event_sent, last_updated.
        # IMPORTANT : plate_db n'est muté QUE par le thread caméra (process,
        # _drain_*, _cleanup). Les workers OCR/réseau ne lisent/écrivent que des
        # files → aucun verrou nécessaire (mêmes garanties qu'avant).
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

        # ── Mesure (chapitre 4 §4.6) ────────────────────────────────────────
        self.measure = get_measurement()
        self._last_detect_ms = 0.0   # latence YOLO de la dernière frame de détection

        self._stop = threading.Event()

        # ── Worker OCR découplé (Step 4) ──────────────────────────────────────
        # Le thread caméra ne fait QUE détecter + tracker + soumettre des crops.
        # EasyOCR + l'ordre de lecture spatial 2D (plate_detection.read_plate_text)
        # tournent ICI → jamais sur la boucle de tracking WebRTC. Borné : avec le
        # gating `ocr_inflight` (≤ 1 crop en vol par track) la file reste petite ;
        # si pleine, on saute la soumission (réessai au prochain cycle).
        ocrq = max(1, getattr(config, 'PLATE_OCR_QUEUE_MAXSIZE', 32))
        self._ocr_jobs: "queue.Queue" = queue.Queue(maxsize=ocrq)
        self._ocr_results: "queue.Queue" = queue.Queue()
        self._ocr_worker = threading.Thread(
            target=self._ocr_loop, name=f"lpr-ocr-{self.cam_id}", daemon=True
        )
        self._ocr_worker.start()

        # ── Worker réseau découplé ────────────────────────────────────────────
        # Le thread caméra ne fait QUE détecter/lire/annoter. La recherche floue
        # et l'envoi d'événement (lents, réseau) sont délégués à ce worker.
        maxq = getattr(config, 'PLATE_LOOKUP_QUEUE_MAXSIZE', 64)
        self._jobs: "queue.Queue" = queue.Queue(maxsize=maxq)
        self._results: "queue.Queue" = queue.Queue()
        self._worker = threading.Thread(
            target=self._lookup_loop, name=f"lpr-lookup-{self.cam_id}", daemon=True
        )
        self._worker.start()

    # ──────────────────────────────────────────────────────────────────────
    # Entrée principale (appelée par TrackingProcessor sur les frames traitées)
    # ──────────────────────────────────────────────────────────────────────
    def process(self, frame: np.ndarray, frame_idx: int) -> None:
        """
        Phase 2 : détecte/lit les plaques sur `frame` et met à jour plate_db +
        _active_ids, SANS dessiner. Les bounding boxes sont récupérées ensuite par
        get_detections() (JSON) pour l'overlay frontend.
        """
        if not plate_detection.LPR_AVAILABLE:
            return

        # 1) Appliquer les résultats revenus des workers (non bloquant) :
        #    - OCR  : nouvelles lectures → vote temporel / finalisation,
        #    - réseau : recherche floue + événement.
        self._drain_ocr()
        self._drain_results()

        # 2) Cadence : ne lancer la détection YOLO qu'1 frame sur N. Entre deux,
        #    on conserve _active_ids/plate_db (l'overlay frontend reste affiché).
        self._proc_count += 1
        if self._proc_count % self.process_every_n != 0:
            return

        _t_det = time.perf_counter()
        detections = detect_plates(frame, confidence_threshold=self.det_conf)
        self._last_detect_ms = (time.perf_counter() - _t_det) * 1000.0

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

            # ── Frame-skipping OCR : soumettre au worker OCR seulement si pas
            #    encore « définitif » (la lecture elle-même est asynchrone) ──
            if not entry["finalized"] and entry["attempts"] < self.max_attempts:
                self._submit_ocr(tid, entry, frame, x, y, w, h)

            # Programmer la résolution réseau dès que la lecture est définitive.
            if entry["finalized"] and entry["plate_text"]:
                self._schedule_lookup(tid, entry, frame)

        self._cleanup(frame_idx)

    def get_detections(self) -> List[Dict]:
        """Détections plaques (JSON) des tracks actifs, pour l'overlay frontend.

        Schéma par détection :
          {type:"plate", track_id, bbox:[x1,y1,x2,y2], label, alert:bool, known:bool}
        """
        out: List[Dict] = []
        if not plate_detection.LPR_AVAILABLE:
            return out
        for tid in self._active_ids:
            entry = self.plate_db.get(tid)
            if not entry:
                continue
            x, y, w, h = entry["bbox"]
            text = entry["plate_text"] or "..."
            if entry["is_blacklisted"]:
                label = f"{text} [BLACKLIST]"
            elif entry["owner_name"]:
                label = f"{text} ({entry['owner_name']})"
            else:
                label = text
            out.append({
                "type": "plate",
                "track_id": tid,
                "bbox": [x, y, x + w, y + h],
                "label": label,
                "alert": bool(entry["is_blacklisted"]),
                "known": entry["vehicle_id"] is not None,
            })
        return out

    def shutdown(self) -> None:
        """Arrête proprement les workers OCR + réseau (appelé à l'arrêt caméra)."""
        self._stop.set()
        for q in (self._ocr_jobs, self._jobs):
            try:
                q.put_nowait(None)        # réveille le worker s'il attend
            except Exception:
                pass
        for worker in (self._ocr_worker, self._worker):
            if worker is not None and worker.is_alive():
                worker.join(timeout=3)

    # ──────────────────────────────────────────────────────────────────────
    # Lecture OCR + vote temporel
    # ──────────────────────────────────────────────────────────────────────
    def _submit_ocr(self, tid: int, entry: Dict, frame: np.ndarray,
                    x: int, y: int, w: int, h: int) -> None:
        """Soumet (thread caméra, NON bloquant) un crop au worker OCR.

        Gating taille/netteté appliqué ici (bon marché) pour ne pas gaspiller le
        worker. Un seul crop « en vol » par track (`ocr_inflight`) → la file reste
        bornée et on ne double-compte pas les tentatives. La lecture EasyOCR + le
        regroupement spatial 2D se font ensuite dans _ocr_loop (hors thread caméra).
        """
        # Un crop est déjà en cours de lecture pour ce track → on attend.
        if entry["ocr_inflight"]:
            return
        # Gating taille : on ignore les plaques trop petites (illisibles).
        if w < self.min_crop_w or h < self.min_crop_h:
            logger.info(f"[LPR][DBG] crop tid={tid} w={w} h={h} GATÉ "  # TEMP DEBUG
                        f"(min w={self.min_crop_w} h={self.min_crop_h})")
            return
        logger.info(f"[LPR][DBG] crop tid={tid} w={w} h={h} -> soumis au worker OCR")  # TEMP DEBUG

        crop = frame[y:y + h, x:x + w]
        if crop is None or crop.size == 0:
            return

        # Gating netteté (optionnel) : on ne consomme pas une tentative sur un
        # crop flou — on attend une meilleure frame.
        if self.crop_min_sharp > 0.0 and self._sharpness(crop) < self.crop_min_sharp:
            return

        # Le crop est une VUE de `frame`, réutilisée par la boucle caméra → copie
        # impérative avant de la confier au worker (sinon corruption mémoire).
        job = {"track_id": tid, "crop": crop.copy()}
        try:
            self._ocr_jobs.put_nowait(job)
            entry["ocr_inflight"] = True
        except queue.Full:
            # Worker OCR saturé → on saute ce cycle (réessai à la prochaine frame).
            pass

    def _drain_ocr(self) -> None:
        """Applique (thread caméra) les lectures OCR produites par le worker :
        comptage des tentatives + vote temporel + finalisation."""
        while True:
            try:
                r = self._ocr_results.get_nowait()
            except queue.Empty:
                break
            entry = self.plate_db.get(r["track_id"])
            if entry is None:
                continue                      # track expiré entre-temps
            entry["ocr_inflight"] = False
            if entry["finalized"]:
                continue
            entry["attempts"] += 1

            # Mesure : latence OCR + mémorisation de la 1re lecture mono-image.
            ocr_ms = float(r.get("ocr_ms", 0.0))
            entry["ocr_ms_sum"] += ocr_ms
            entry["ocr_count"] += 1
            if entry.get("first_text") is None and r["text"]:
                entry["first_text"] = r["text"]      # lecture mono-image (1 passe OCR)
                entry["first_ocr_ms"] = ocr_ms

            logger.info(f"[LPR][DBG] résultat OCR tid={r['track_id']} "  # TEMP DEBUG
                        f"text='{r['text']}' conf={r['conf']:.2f} "
                        f"(ocr_min={self.ocr_min}) attempts={entry['attempts']}")
            self._apply_reading(entry, r["text"], r["conf"])

            # Mesure : émettre une seule fois quand la plaque devient définitive
            # (compare lecture mono-image vs consensus voté → tableau 4.6).
            if entry["finalized"] and not entry.get("read_emitted"):
                self._emit_plate_read(r["track_id"], entry)
                entry["read_emitted"] = True

    def _apply_reading(self, entry: Dict, text: str, conf: float) -> None:
        """Agrège une lecture OCR dans l'entrée (vote temporel / finalisation)."""
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

    def _ocr_loop(self) -> None:
        """Boucle du worker OCR : lit les crops (EasyOCR + ordre de lecture spatial
        2D) hors du thread caméra et renvoie (track_id, text, conf) au thread caméra
        via _ocr_results. Aucune écriture dans plate_db ici (thread-safe par design)."""
        while not self._stop.is_set():
            try:
                job = self._ocr_jobs.get(timeout=0.5)
            except queue.Empty:
                continue
            if job is None:                   # sentinelle d'arrêt
                break
            try:
                _t_ocr = time.perf_counter()
                text, conf = read_plate_text(job["crop"])
                ocr_ms = (time.perf_counter() - _t_ocr) * 1000.0
            except Exception as e:
                logger.error(f"[LPR][cam={self.cam_name}] worker OCR : {e}")
                text, conf, ocr_ms = "", 0.0, 0.0
            self._ocr_results.put(
                {"track_id": job["track_id"], "text": text, "conf": conf, "ocr_ms": ocr_ms}
            )

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
            "ocr_inflight": False,
            "vehicle_id": None, "is_blacklisted": False, "owner_name": None,
            "looked_up_for": None, "lookup_inflight": None,
            "event_sent": False, "last_updated": frame_idx,
            # ── Mesure (§4.6) : latence + comparaison mono-image / vote ──
            "created_ts": time.time(),   # pour le temps jusqu'à finalisation
            "first_text": None,          # 1re lecture OCR (mono-image)
            "first_ocr_ms": None,
            "ocr_ms_sum": 0.0, "ocr_count": 0,
            "read_emitted": False,
        }

    def _emit_plate_read(self, tid: int, entry: Dict) -> None:
        """Émet un événement `plate_read` (mesure §4.6) à la finalisation d'une plaque.

        Compare la lecture MONO-IMAGE (1re passe OCR) au consensus VOTÉ, et fournit
        les latences (détection YOLO, OCR, temps total jusqu'à finalisation) pour
        que tools/analyze_metrics.py calcule CER + exactitude plaque entière et la
        latence du pipeline LPR, mono vs vote temporel.
        """
        n = entry.get("ocr_count", 0)
        created = entry.get("created_ts")
        self.measure.emit(
            "plate_read",
            camera_id=self.cam_id,
            track_id=tid,
            mono=(entry.get("first_text") or ""),     # lecture mono-image
            voted=(entry.get("plate_text") or ""),    # consensus vote temporel
            conf=round(float(entry.get("ocr_conf", 0.0)), 3),
            attempts=entry.get("attempts"),
            n_readings=len(entry.get("readings", [])),
            detect_ms=round(self._last_detect_ms, 2),
            first_ocr_ms=(round(entry["first_ocr_ms"], 2)
                          if entry.get("first_ocr_ms") is not None else None),
            avg_ocr_ms=(round(entry["ocr_ms_sum"] / n, 2) if n else None),
            time_to_finalize_ms=(round((time.time() - created) * 1000.0, 1)
                                 if created else None),
            expected=self.measure.get_expected_plate(),
        )

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
        # Mesure (§4.6) : trace brute de la recherche floue (plaque lue → match).
        self.measure.emit(
            "plate_lookup",
            camera_id=self.cam_id,
            query=plate_text,
            matched=bool(match),
            matched_plate=(match.get("plate") or match.get("plate_number")) if match else None,
            score=(match.get("score") if match else None),
            vehicle_id=(match.get("id") if match else None),
            is_blacklisted=bool(match.get("is_blacklisted")) if match else False,
            expected=self.measure.get_expected_plate(),
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

    # Phase 2 : _annotate() SUPPRIMÉ — le Core ne dessine plus les plaques.
    # Les boîtes sont exposées en JSON via get_detections() et dessinées par le
    # frontend sur un <canvas> superposé à la vidéo WebRTC.

    def _cleanup(self, frame_idx: int) -> None:
        expired = [tid for tid, e in self.plate_db.items()
                   if frame_idx - e["last_updated"] > self.ttl_frames]
        for tid in expired:
            del self.plate_db[tid]

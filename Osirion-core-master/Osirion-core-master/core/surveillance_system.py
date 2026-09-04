# core/surveillance_system.py
"""
Système de surveillance multi-caméras avec reconnaissance faciale
"""
import threading
import queue
import time
import shutil
from pathlib import Path
from typing import List, Dict, Set

from core.trackers.oc_sort import OCSortTrackerAdapter
from services.camera_fetching_service import fetch_camera_list
from services.mediamtx_path_service import sync_paths, managed_paths_health
from services.hik_stream_resolver import resolve_stream_url, resolver_health
from core.camera_manager import CameraCapture
from core.tracking_processor import TrackingProcessor
from core import event_dispatch
from utils.logger import get_logger
from utils.measurement import get_measurement
from utils.gpu_monitor import get_gpu_stats

logger = get_logger(__name__)


class SurveillanceSystem:
    """Système principal de surveillance multi-caméras"""
    
    def __init__(self, config):
        self.config = config
        self.active_cameras: List[Dict] = []
        
        # Structures globales
        self.trackers = {}
        self.track_id_to_person = {}
        self.current_frame_idx = {}
        self.frame_queues = {}
        self.result_frames = {}
        # Phase 2 : le Core ne produit plus d'images annotées. Chaque caméra publie
        # un payload de métadonnées JSON (bounding boxes) que le serveur web diffuse
        # via Socket.IO ('metadata'). La vidéo passe par MediaMTX (WebRTC), pas ici.
        self.result_metadata = {}             # {cam_id: {"seq": int, "payload": {...}}}
        self.result_lock = threading.Lock()   # verrou global (routes REST)
        self.result_locks = {}                # verrous par caméra (streaming)
        self.stop_event = threading.Event()   # arrêt GLOBAL du système

        # ── Cycle de vie PAR CAMÉRA (hot-add / hot-remove) ───────────────────
        # Chaque caméra a son propre event d'arrêt → on peut l'arrêter seule sans
        # toucher aux autres. self.stop() déclenche tous ces events + le global.
        self.camera_stop_events: Dict[int, threading.Event] = {}   # {cam_id: Event}
        self.camera_threads: Dict[int, List] = {}                  # {cam_id: [capture_thread, processing_thread]}
        self.camera_captures: Dict[int, CameraCapture] = {}        # {cam_id: CameraCapture} — pour la santé
        self.camera_processors: Dict[int, object] = {}             # {cam_id: TrackingProcessor} — pour la mesure (latence)
        # Sérialise les ajouts/retraits/réconciliations de caméras (démarrage + supervision).
        self.camera_lock = threading.Lock()
        self._supervisor_thread = None
        self._health_monitor_thread = None

        self.threads = []
        self.web_server = None
    
    def _add_camera(self, cam: Dict) -> bool:
        """Initialise les structures et démarre les threads (capture + traitement)
        d'UNE caméra. Idempotent. À APPELER SOUS self.camera_lock.

        Retourne True si la caméra a été démarrée, False si elle l'était déjà.
        """
        cam_id = cam["id"]
        if cam_id in self.camera_stop_events:
            return False  # déjà active

        # ── Structures de données propres à cette caméra ──
        self.frame_queues[cam_id] = queue.Queue(maxsize=self.config.FRAME_QUEUE_MAXSIZE)
        self.result_frames[cam_id] = None
        self.result_metadata[cam_id] = None
        self.result_locks[cam_id] = threading.Lock()
        self.trackers[cam_id] = OCSortTrackerAdapter(self.config.OC_SORT_ARGS)
        self.track_id_to_person[cam_id] = {}
        self.current_frame_idx[cam_id] = 0

        # Event d'arrêt PROPRE À CETTE CAMÉRA (hot-remove sans toucher aux autres).
        cam_stop = threading.Event()
        self.camera_stop_events[cam_id] = cam_stop

        # Thread de capture RTSP
        capture = CameraCapture(
            cam=cam,
            frame_queue=self.frame_queues[cam_id],
            stop_event=cam_stop,
            config=self.config,
        )
        capture_thread = threading.Thread(
            target=capture.run, daemon=True, name=f"capture-{cam_id}"
        )

        # Thread de traitement
        processor = TrackingProcessor(
            cam=cam,
            frame_queue=self.frame_queues[cam_id],
            result_frames=self.result_frames,
            result_metadata=self.result_metadata,
            result_lock=self.result_locks[cam_id],
            tracker=self.trackers[cam_id],
            frame_idx_container=self.current_frame_idx,
            stop_event=cam_stop,
            config=self.config,
        )
        processing_thread = threading.Thread(
            target=processor.run, daemon=True, name=f"processor-{cam_id}"
        )

        capture_thread.start()
        processing_thread.start()
        self.camera_threads[cam_id] = [capture_thread, processing_thread]
        self.camera_captures[cam_id] = capture       # exposé pour la santé caméras
        self.camera_processors[cam_id] = processor   # exposé pour la mesure (latence)
        self.threads.extend([capture_thread, processing_thread])

        # Publier la caméra par REMPLACEMENT ATOMIQUE de la référence de liste :
        # les lecteurs (serveur web) itèrent l'ancienne liste sans risque, le
        # prochain accès voit la nouvelle. Évite toute mutation concurrente in-place.
        self.active_cameras = self.active_cameras + [cam]
        logger.info(
            f"Caméra {cam_id} ({cam.get('cam_name')}) démarrée.",
            extra={'camera_id': cam_id}
        )
        return True

    def _remove_camera(self, cam_id: int) -> bool:
        """Arrête proprement les threads d'UNE caméra et nettoie ses structures.
        À APPELER SOUS self.camera_lock.
        """
        cam_stop = self.camera_stop_events.get(cam_id)
        if cam_stop is None:
            return False  # pas active

        cam_name = next(
            (c.get("cam_name") for c in self.active_cameras if c["id"] == cam_id), cam_id
        )
        logger.info(
            f"Retrait de la caméra {cam_id} ({cam_name})...", extra={'camera_id': cam_id}
        )

        # 1) Retirer des caméras actives (remplacement atomique) → plus de nouveau
        #    viewer, plus listée par /api/cameras.
        self.active_cameras = [c for c in self.active_cameras if c["id"] != cam_id]

        # 2) Signaler l'arrêt aux threads capture + traitement de cette caméra
        #    (interrompt aussi un éventuel backoff de reconnexion en cours).
        cam_stop.set()

        # 3) Attendre la fin des threads (borné : ne bloque pas la supervision).
        for t in self.camera_threads.get(cam_id, []):
            t.join(timeout=5)
        self.threads = [t for t in self.threads if t.is_alive()]

        # 4) Nettoyer les structures (après l'arrêt des threads → pas d'écriture
        #    concurrente). Le serveur web tolère l'absence de clé (.get + fallback).
        self.camera_stop_events.pop(cam_id, None)
        self.camera_threads.pop(cam_id, None)
        self.camera_captures.pop(cam_id, None)
        self.camera_processors.pop(cam_id, None)
        self.frame_queues.pop(cam_id, None)
        self.result_frames.pop(cam_id, None)
        self.trackers.pop(cam_id, None)
        self.track_id_to_person.pop(cam_id, None)
        self.current_frame_idx.pop(cam_id, None)
        with self.result_lock:
            self.result_metadata.pop(cam_id, None)
        self.result_locks.pop(cam_id, None)

        logger.info(f"Caméra {cam_id} retirée.", extra={'camera_id': cam_id})
        return True

    def camera_health(self) -> List[Dict]:
        """Instantané de santé par caméra (pour la page « Santé des caméras »).

        Lecture BEST-EFFORT, sans verrou : `active_cameras` est remplacée de façon
        atomique, et les compteurs lus peuvent être légèrement obsolètes — ce qui
        est sans conséquence pour un affichage temps réel. États possibles :
        online | stalled (frames figées) | connecting | offline | stopped.
        """
        cams = self.active_cameras          # référence atomique
        out: List[Dict] = []
        for cam in cams:
            cam_id = cam["id"]
            capture = self.camera_captures.get(cam_id)
            threads = self.camera_threads.get(cam_id, [])
            threads_alive = bool(threads) and all(t.is_alive() for t in threads)
            h = capture.health() if capture is not None else {}

            meta = self.result_metadata.get(cam_id)
            last_seq = meta.get("seq") if isinstance(meta, dict) else None

            connected = h.get("connected", False)
            attempts = h.get("reconnection_attempts", 0)
            age = h.get("last_frame_age_s")
            max_attempts = getattr(self.config, "MAX_RECONNECTION_ATTEMPTS", 5)
            if not threads_alive:
                state = "stopped"
            elif not connected:
                state = "offline" if attempts >= max_attempts else "connecting"
            elif age is not None and age > 5:
                state = "stalled"     # flux ouvert mais plus de frames fraîches
            else:
                state = "online"

            out.append({
                "id": cam_id,
                "name": cam.get("cam_name"),
                "location": cam.get("location"),
                "state": state,
                "threads_alive": threads_alive,
                "last_processed_seq": last_seq,
                **h,
            })
        return out

    def _sync_mediamtx_paths(self, desired: Dict[int, Dict]) -> None:
        """Synchronise les chemins MediaMTX (1 par caméra) avec l'ensemble voulu.

        `desired` : {cam_id: cam_dict}. No-op si MANAGE_MEDIAMTX_PATHS=false
        (déploiement sans MediaMTX ou chemins gérés statiquement). Best-effort :
        n'interrompt JAMAIS le démarrage/la supervision des caméras.
        """
        if not getattr(self.config, 'MANAGE_MEDIAMTX_PATHS', True):
            return
        try:
            sync_paths(
                api_base=getattr(self.config, 'MEDIAMTX_API_BASE', 'http://mediamtx:9997'),
                desired=desired,
                transport=getattr(self.config, 'MEDIAMTX_RTSP_TRANSPORT', 'tcp'),
                close_after=getattr(self.config, 'MEDIAMTX_ON_DEMAND_CLOSE_AFTER', '30s'),
                transcode_encoder=getattr(self.config, 'HIK_TRANSCODE_ENCODER', 'h264_nvenc'),
                transcode_flags=getattr(self.config, 'HIK_TRANSCODE_FLAGS', ''),
                hik_start_timeout=getattr(self.config, 'HIK_ONDEMAND_START_TIMEOUT', '30s'),
                healthy=self._healthy_camera_ids(),
            )
        except Exception:
            logger.error("Échec synchro des chemins MediaMTX", exc_info=True)

    def _healthy_camera_ids(self) -> Set[int]:
        """Caméras dont la capture est VIVANTE (flux ouvert, frames fraîches).

        Sert à protéger un chemin MediaMTX qui diffuse encore alors que son URL
        n'est plus résoluble : une URL rtsp_s déjà établie continue de fonctionner
        tant que le relais tient sa session, et supprimer ce chemin couperait un
        flux sain. Lecture best-effort, sans verrou (cf. camera_health).
        """
        healthy: Set[int] = set()
        for cam_id, cap in list(self.camera_captures.items()):
            try:
                h = cap.health() or {}
                age = h.get("last_frame_age_s")
                if h.get("connected") and age is not None and age <= 5:
                    healthy.add(cam_id)
            except Exception:
                continue
        return healthy

    def _resolve_hik_urls(self, desired: Dict[int, Dict]) -> None:
        """Résout À LA DEMANDE l'URL RTSP des caméras HikCentral (source_type=
        "hikcentral"), qui n'ont pas de rtsp_url stockée, et l'injecte dans le
        cam_dict — consommée ensuite par le relais MediaMTX ET la capture.

        Best-effort : une caméra dont l'URL ne se résout pas (liaison agence
        coupée, passerelle en 502) reste sans rtsp_url → `sync_paths` SUPPRIME alors
        son chemin MediaMTX s'il existe et que la capture est morte, pour ne pas y
        laisser un relais se relancer en boucle contre une passerelle qui ne répond
        plus. N'impacte pas les autres.

        Le rafraîchissement forcé demandé ici n'est qu'une INTENTION : le résolveur
        la neutralise dès qu'il constate des échecs (cf. hik_stream_resolver), pour
        ne pas contourner le cache backend au moment précis où la passerelle sature.
        """
        for cam in desired.values():
            if cam.get("source_type") != "hikcentral" or cam.get("rtsp_url"):
                continue
            # Si la caméra est DÉJÀ en difficulté (capture non connectée / frames
            # trop vieilles), l'URL rtsp_s a probablement EXPIRÉ (la passerelle SMS
            # renvoie 5XX en boucle) → forcer une URL fraîche (bypass du cache
            # backend) pour auto-guérir, au lieu d'attendre l'expiration du cache
            # (jusqu'à 240 s). Sinon, résolution normale (cache).
            force = False
            cap = self.camera_captures.get(cam["id"])
            if cap is not None:
                try:
                    h = cap.health() or {}
                    age = h.get("last_frame_age_s")
                    if not h.get("connected", True) or (age is not None and age > 10):
                        force = True
                except Exception:
                    pass
            url = resolve_stream_url(cam["id"], refresh=force)
            if url:
                cam["rtsp_url"] = url

    def _reconcile_cameras(self) -> None:
        """Compare l'état backend à l'état courant et applique les différences À
        CHAUD : ajout/(ré)activation, désactivation/suppression, et résurrection
        d'une caméra dont un thread s'est arrêté de façon inattendue.
        """
        cameras = fetch_camera_list()

        # GARDE-FOU anti-coupure : fetch_camera_list() renvoie [] AUSSI BIEN sur
        # erreur réseau/HTTP que sur « 0 caméra ». Impossible de distinguer les
        # deux → sur liste vide on NE RETIRE RIEN (sinon un simple incident API
        # démonterait toutes les caméras). Rien à ajouter d'une liste vide non plus.
        if not cameras:
            logger.debug(
                "Supervision caméras : liste vide (erreur API ou aucune caméra) — aucun changement."
            )
            return

        desired = {c["id"]: c for c in cameras if c.get("is_active", False)}

        # Résout l'URL des caméras HikCentral (pas de rtsp_url stockée) AVANT tout :
        # le relais MediaMTX comme la capture en ont besoin.
        self._resolve_hik_urls(desired)

        # Synchronise les chemins MediaMTX (création/maj/suppression) avec l'état
        # voulu AVANT d'ajuster les threads caméra, qui lisent rtsp://.../cam<id>.
        # Idempotent et best-effort.
        self._sync_mediamtx_paths(desired)

        with self.camera_lock:
            current_ids = set(self.camera_stop_events.keys())
            desired_ids = set(desired.keys())

            # 1) Ajouts / (ré)activations
            for cam_id in desired_ids - current_ids:
                try:
                    self._add_camera(desired[cam_id])
                except Exception:
                    logger.error(
                        f"Échec ajout à chaud caméra {cam_id}",
                        exc_info=True, extra={'camera_id': cam_id}
                    )

            # 2) Retraits (désactivée côté backend ou supprimée)
            for cam_id in current_ids - desired_ids:
                try:
                    self._remove_camera(cam_id)
                except Exception:
                    logger.error(
                        f"Échec retrait à chaud caméra {cam_id}",
                        exc_info=True, extra={'camera_id': cam_id}
                    )

            # 3) Caméras déjà actives : résurrection si un thread est mort
            #    (exception non gérée) → redémarrage propre de la caméra.
            for cam_id in desired_ids & current_ids:
                threads = self.camera_threads.get(cam_id, [])
                if threads and any(not t.is_alive() for t in threads):
                    logger.warning(
                        f"Caméra {cam_id} : thread arrêté de façon inattendue — redémarrage.",
                        extra={'camera_id': cam_id}
                    )
                    self._remove_camera(cam_id)
                    self._add_camera(desired[cam_id])
                    continue

                # Les seuils/régimes d'effectif sont de la configuration métier :
                # les appliquer à chaud sans couper le flux vidéo.
                processor = self.camera_processors.get(cam_id)
                if processor is not None:
                    try:
                        processor.update_camera_config(desired[cam_id])
                    except Exception:
                        logger.warning(
                            f"Caméra {cam_id} : mise à jour de la politique "
                            "d'effectif impossible — nouvel essai au prochain cycle.",
                            exc_info=True,
                            extra={'camera_id': cam_id},
                        )

            # Met aussi à jour les métadonnées exposées (nom, emplacement,
            # politique) par remplacement atomique de la liste.
            running = set(self.camera_stop_events)
            self.active_cameras = [
                desired[camera_id] for camera_id in desired_ids if camera_id in running
            ]

    def _supervise_loop(self) -> None:
        """Boucle de supervision : réconcilie périodiquement avec le backend."""
        interval = getattr(self.config, 'CAMERA_REFRESH_SECONDS', 15)
        logger.info(f"Supervision des caméras active (rafraîchissement toutes les {interval}s).")
        # stop_event.wait() renvoie True dès que l'arrêt GLOBAL est demandé → sort.
        while not self.stop_event.wait(interval):
            try:
                self._reconcile_cameras()
            except Exception:
                logger.error("Erreur dans la boucle de supervision des caméras", exc_info=True)
        logger.info("Supervision des caméras arrêtée.")

    def _health_monitor_loop(self) -> None:
        """Propage rapidement la disponibilité vidéo aux machines métier."""
        interval = max(
            0.5,
            float(getattr(self.config, "CAMERA_HEALTH_DECISION_INTERVAL", 2.0)),
        )
        logger.info(
            "Décisions liées à la santé caméra actives (toutes les %.1fs).",
            interval,
        )
        while not self.stop_event.is_set():
            now = time.time()
            try:
                for row in self.camera_health():
                    processor = self.camera_processors.get(row["id"])
                    if processor is not None:
                        processor.update_camera_health(row.get("state"), now=now)
            except Exception:
                logger.error(
                    "Erreur dans la propagation de santé caméra", exc_info=True
                )
            if self.stop_event.wait(interval):
                break

    def _measure_sampler_loop(self) -> None:
        """Échantillonneur de MESURE (chapitre 4) : émet périodiquement un
        `system_sample` dans metrics.jsonl — débit/latence par caméra, taux de
        succès du cache, occupation GPU — pour les tableaux 4.4 et 4.5.

        Le débit RÉEL de traitement par caméra est déduit du nombre de frames
        inférées sur l'intervalle (n_face / durée), indépendamment de la cadence
        de capture. Best-effort : aucune erreur n'interrompt la boucle.
        """
        measure = get_measurement()
        interval = max(1, int(getattr(self.config, 'MEASURE_SAMPLE_SECONDS', 5)))
        logger.info(f"[MESURE] échantillonnage système actif (toutes les {interval}s).")
        last = time.monotonic()
        while not self.stop_event.wait(interval):
            now = time.monotonic()
            dt = now - last
            last = now
            try:
                cams_payload = []
                health = {h["id"]: h for h in self.camera_health()}
                for cam in self.active_cameras:
                    cid = cam["id"]
                    proc = self.camera_processors.get(cid)
                    snap = proc.latency_snapshot(reset=True) if proc is not None else {}
                    h = health.get(cid, {})
                    n_det = snap.get("n_detections", 0)
                    cams_payload.append({
                        "id": cid,
                        "name": cam.get("cam_name"),
                        "capture_fps": h.get("fps"),
                        "state": h.get("state"),
                        # Débit réel d'inférence = frames traitées / durée d'intervalle.
                        "processed_fps": round(n_det / dt, 2) if dt > 0 else None,
                        "detect_ms": snap.get("detect_ms"),
                        "frame_ms": snap.get("frame_ms"),
                        "n_processed": n_det,
                    })
                cache = {}
                disk_target = Path("/app/observation_runs")
                if not disk_target.exists():
                    disk_target = Path("/app")
                total_b, used_b, free_b = shutil.disk_usage(disk_target)
                measure.emit(
                    "system_sample",
                    interval_s=round(dt, 2),
                    n_cameras=len(self.active_cameras),
                    cameras=cams_payload,
                    cache=cache,
                    gpu=get_gpu_stats(),
                    # Santé de l'INGESTION (passerelle HikCentral + disjoncteur).
                    # Sans ces compteurs, la campagne d'août 2026 a exigé de croiser
                    # 363 Mo de journaux MediaMTX pour comprendre que la panne venait
                    # de la passerelle et non des caméras. Ils rendent metrics.jsonl
                    # auto-suffisant pour ce diagnostic.
                    ingest={
                        **resolver_health(),
                        **managed_paths_health(
                            getattr(self.config, 'MEDIAMTX_API_BASE',
                                    'http://mediamtx:9997')
                        ),
                    },
                    disk={
                        "path": str(disk_target),
                        "total_gb": round(total_b / 1024 ** 3, 2),
                        "used_gb": round(used_b / 1024 ** 3, 2),
                        "free_gb": round(free_b / 1024 ** 3, 2),
                        "used_percent": round(100 * used_b / total_b, 1) if total_b else 0,
                    },
                )
            except Exception:
                logger.error("[MESURE] erreur dans l'échantillonneur système", exc_info=True)
        logger.info("[MESURE] échantillonnage système arrêté.")

    def run(self):
        """Démarre le système de surveillance (avec supervision à chaud des caméras)."""
        event_dispatch.start()   # dispatcher d'événements découplé (Event Engine)
        cameras = fetch_camera_list()
        logger.info(f"Caméras trouvées au total : {len(cameras)}")
        active = [cam for cam in cameras if cam.get("is_active", False)]
        if not active:
            logger.warning(
                "Aucune caméra active au démarrage. Le système démarre et attend "
                "(la supervision les prendra en compte dès leur activation)."
            )
        else:
            active_cam_strs = [f"{c['cam_name']} (id={c['id']}, {c['location']})" for c in active]
            logger.info(f"Caméras actives au démarrage : {active_cam_strs}")

        # Déclare les chemins MediaMTX (1 par caméra) AVANT de démarrer les threads
        # de capture, qui lisent rtsp://mediamtx:8554/cam<id>.
        self._sync_mediamtx_paths({c["id"]: c for c in active})

        with self.camera_lock:
            for cam in active:
                try:
                    self._add_camera(cam)
                except Exception:
                    logger.error(
                        f"Échec démarrage caméra {cam.get('id')}",
                        exc_info=True, extra={'camera_id': cam.get('id')}
                    )

        # Thread de supervision : prise en compte à chaud des changements backend.
        interval = getattr(self.config, 'CAMERA_REFRESH_SECONDS', 15)
        if interval and interval > 0:
            self._supervisor_thread = threading.Thread(
                target=self._supervise_loop, daemon=True, name="camera-supervisor"
            )
            self._supervisor_thread.start()
        else:
            logger.info("Supervision des caméras désactivée (CAMERA_REFRESH_SECONDS=0).")

        self._health_monitor_thread = threading.Thread(
            target=self._health_monitor_loop,
            daemon=True,
            name="camera-health-decisions",
        )
        self._health_monitor_thread.start()

        # Échantillonneur de MESURE (chapitre 4) — démarré seulement si activé.
        if get_measurement().enabled:
            self._measure_sampler_thread = threading.Thread(
                target=self._measure_sampler_loop, daemon=True, name="measure-sampler"
            )
            self._measure_sampler_thread.start()

        time.sleep(3)
        logger.info("Système multi-caméras prêt en mode headless (sans affichage)")
        logger.info("Le traitement de reconnaissance faciale est actif en arrière-plan")
        logger.info("Appuyez sur Ctrl+C pour quitter")

        return True
    
    def enable_web_streaming(self, host=None, port=None):
        """
        Active le streaming web via WebSocket (optionnel)
        
        Args:
            host: Adresse IP à écouter (défaut: depuis config)
            port: Port à écouter (défaut: depuis config)
        
        Returns:
            WebStreamingServer instance
        """
        from core.web_streaming import WebStreamingServer
        
        host = host or self.config.WEB_STREAMING_HOST
        port = port or self.config.WEB_STREAMING_PORT
        
        self.web_server = WebStreamingServer(self, host=host, port=port)
        self.web_server.start()
        
        return self.web_server
    
    def stop(self):
        """Arrête proprement le système"""
        logger.info("Arrêt du système en cours...")
        # Arrêt GLOBAL (boucle de supervision) + arrêt de CHAQUE caméra : les
        # threads capture/traitement écoutent leur event par caméra, pas le global.
        self.stop_event.set()
        with self.camera_lock:
            for ev in self.camera_stop_events.values():
                ev.set()

        # Arrêter le serveur web si actif
        if self.web_server:
            self.web_server.stop()

        event_dispatch.stop()   # arrêt du dispatcher d'événements

        time.sleep(0.5)
        logger.info("Application multi-caméras fermée proprement")

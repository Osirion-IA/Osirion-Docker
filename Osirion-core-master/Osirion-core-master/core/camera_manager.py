# core/camera_manager.py
"""
Gestion de la capture RTSP avec reconnexion automatique
"""
import os
import re
import cv2
import time
from typing import Optional, Dict
import queue
from utils.logger import get_logger

logger = get_logger(__name__)


def _mask_rtsp_url(url: str) -> str:
    """Fix #7 : masque les credentials dans une URL RTSP pour les logs.
    rtsp://admin:secret@192.168.1.1/stream → rtsp://***@192.168.1.1/stream
    """
    return re.sub(r'(rtsp://)([^@]+@)', r'\1***@', url)


class CameraCapture:
    """Gère la capture RTSP d'une caméra avec reconnexion automatique"""
    
    def __init__(self, cam: Dict, frame_queue: queue.Queue, stop_event, config):
        self.cam_id = cam["id"]
        self.cam_name = cam["cam_name"]
        self.config = config

        # Source de capture (architecture VMS — Phase 2). Si READ_FROM_MEDIAMTX,
        # le Core lit le flux REPUBLIÉ par MediaMTX (rtsp://<base>/cam<id>) au lieu
        # d'ouvrir une 2e connexion vers la caméra physique : une seule connexion
        # caméra (MediaMTX), partagée entre l'IA et la vidéo navigateur.
        if getattr(config, 'READ_FROM_MEDIAMTX', False):
            base = getattr(config, 'MEDIAMTX_RTSP_BASE', 'mediamtx:8554')
            self.rtsp_url = f"rtsp://{base}/cam{self.cam_id}"
            self.source_kind = "MediaMTX (republié)"
        else:
            self.rtsp_url = cam["rtsp_url"]
            self.source_kind = "caméra directe"

        logger.info(
            f"Caméra {self.cam_id} ({self.cam_name}) — source de capture : "
            f"{self.source_kind} [{_mask_rtsp_url(self.rtsp_url)}]",
            extra={'camera_id': self.cam_id}
        )

        self.frame_queue = frame_queue
        self.stop_event = stop_event

        self.cap: Optional[cv2.VideoCapture] = None
        self.reconnection_attempts = 0
        self.frame_failures = 0

        # ── Métriques de santé (lues par la page « Santé des caméras ») ──────
        # Écrites par le thread de capture, lues par le thread web (snapshot
        # best-effort : une légère obsolescence est acceptable pour un affichage).
        self.connected = False                 # flux RTSP ouvert et lisible
        self.frames_captured = 0               # total de frames lues avec succès
        self.reconnections = 0                 # nb de reprises après coupure
        self.fps = 0.0                         # cadence de capture (EMA)
        self.last_frame_monotonic: Optional[float] = None   # horodatage dernière frame OK
        self.started_at = time.monotonic()     # pour l'uptime du thread

    def health(self) -> Dict:
        """Instantané des métriques de santé de cette caméra (thread-safe en lecture)."""
        now = time.monotonic()
        age = None if self.last_frame_monotonic is None else round(now - self.last_frame_monotonic, 1)
        return {
            "connected": self.connected,
            "fps": round(self.fps, 1),
            "frames_captured": self.frames_captured,
            "reconnections": self.reconnections,
            "reconnection_attempts": self.reconnection_attempts,
            "last_frame_age_s": age,
            "source_kind": self.source_kind,
            "uptime_s": round(now - self.started_at, 1),
        }

    def _note_frame(self) -> None:
        """Met à jour les compteurs/FPS à chaque frame lue (EMA lissée)."""
        self.frames_captured += 1
        t = time.monotonic()
        if self.last_frame_monotonic is not None:
            dt = t - self.last_frame_monotonic
            if dt > 0:
                inst = 1.0 / dt
                self.fps = inst if self.fps == 0.0 else (0.9 * self.fps + 0.1 * inst)
        self.last_frame_monotonic = t

    def connect_camera(self) -> Optional[cv2.VideoCapture]:
        """Tente de se connecter à la caméra (TCP forcé pour éviter les erreurs de décodage H.264 UDP)"""
        os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"
        # Backend FFmpeg explicite (cv2.CAP_FFMPEG) : sans lui, une URL RTSP contenant
        # un '%' (ex. mot de passe encodé '%40' pour '@') est prise par OpenCV pour un
        # motif de séquence d'images (cap_images) → "expected '0?[1-9][du]' pattern".
        new_cap = cv2.VideoCapture(self.rtsp_url, cv2.CAP_FFMPEG)
        new_cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        if new_cap.isOpened():
            return new_cap
        new_cap.release()
        return None
    
    def _reconnect_loop(self) -> bool:
        """Reconnexion RTSP avec backoff exponentiel, SANS abandon définitif.

        Boucle jusqu'à rétablir le flux. Retourne True dès qu'une connexion est
        rétablie, False UNIQUEMENT si l'arrêt est demandé (stop_event). Ainsi une
        caméra qui revient après une LONGUE coupure est reprise automatiquement,
        sans redémarrage du Core (corrige l'ancien abandon après
        MAX_RECONNECTION_ATTEMPTS).
        """
        # Libérer la connexion morte avant de retenter (évite aussi le crash
        # historique : self.cap laissé à None puis self.cap.read()).
        if self.cap is not None:
            self.cap.release()
            self.cap = None
        self.connected = False     # santé : flux coupé pendant la reconnexion
        self.fps = 0.0

        while not self.stop_event.is_set():
            # Backoff exponentiel plafonné. L'exposant est borné (≤ 16) pour éviter
            # tout débordement après de très nombreuses tentatives ; une fois le
            # plafond atteint, on retente à intervalle constant (MAX_RECONNECTION_DELAY).
            exp = min(self.reconnection_attempts, 16)
            delay = min(
                self.config.RECONNECTION_BASE_DELAY * (2 ** exp),
                self.config.MAX_RECONNECTION_DELAY,
            )
            attempt = self.reconnection_attempts + 1

            # Au-delà de MAX_RECONNECTION_ATTEMPTS on NE quitte PLUS : on signale
            # simplement l'état dégradé (ERROR) et on continue au délai plafond.
            if self.reconnection_attempts >= self.config.MAX_RECONNECTION_ATTEMPTS:
                logger.error(
                    f"Caméra {self.cam_id} ({self.cam_name}) toujours injoignable "
                    f"après {self.reconnection_attempts} tentatives — nouvel essai "
                    f"dans {delay:.1f}s (reconnexion maintenue).",
                    extra={'camera_id': self.cam_id, 'attempt': attempt, 'delay': delay},
                )
            else:
                logger.info(
                    f"Caméra {self.cam_id} : attente de {delay:.1f}s avant reconnexion "
                    f"(tentative {attempt}).",
                    extra={'camera_id': self.cam_id, 'delay': delay, 'attempt': attempt},
                )

            # Attente INTERRUPTIBLE : un arrêt demandé pendant le backoff sort
            # immédiatement (pas de blocage jusqu'à 30s au shutdown / hot-remove).
            if self.stop_event.wait(delay):
                return False

            new_cap = self.connect_camera()
            if new_cap is not None:
                self.cap = new_cap
                logger.info(
                    f"Caméra {self.cam_id} ({self.cam_name}) reconnectée avec succès "
                    f"(après {attempt} tentative(s)).",
                    extra={'camera_id': self.cam_id},
                )
                self.reconnection_attempts = 0
                self.frame_failures = 0
                self.connected = True       # santé : flux rétabli
                self.reconnections += 1
                return True

            self.reconnection_attempts += 1

        return False
    
    def run(self):
        """Boucle principale de capture (reconnexion automatique illimitée)"""
        # Connexion initiale
        logger.info(
            f"Connexion à la caméra {self.cam_id} ({self.cam_name})...",
            extra={'camera_id': self.cam_id}
        )
        self.cap = self.connect_camera()
        if self.cap is None:
            # On NE QUITTE PLUS au premier échec : on bascule en reconnexion
            # automatique (la caméra peut être encore en train de démarrer, ou
            # MediaMTX pas encore prêt à republier le flux).
            logger.warning(
                f"Caméra {self.cam_id} ({self.cam_name}) : flux RTSP indisponible au "
                f"démarrage, passage en reconnexion automatique...",
                extra={'camera_id': self.cam_id, 'rtsp_url': _mask_rtsp_url(self.rtsp_url)}
            )
            if not self._reconnect_loop():
                return  # arrêt demandé avant toute connexion
        else:
            self.connected = True   # santé : flux ouvert au démarrage
            logger.info(
                f"Caméra {self.cam_id} ({self.cam_name}) connectée avec succès",
                extra={'camera_id': self.cam_id}
            )

        while not self.stop_event.is_set():
            ret, frame = self.cap.read()

            if not ret:
                self.frame_failures += 1

                # Déclencher une reconnexion après plusieurs échecs consécutifs
                if self.frame_failures >= self.config.FRAME_FAILURE_THRESHOLD:
                    logger.warning(
                        f"Caméra {self.cam_id} ({self.cam_name}) : "
                        f"{self.frame_failures} échecs consécutifs, reconnexion...",
                        extra={'camera_id': self.cam_id, 'frame_failures': self.frame_failures}
                    )
                    # Reconnexion illimitée : ne rend False que si l'arrêt est demandé.
                    if not self._reconnect_loop():
                        break
                else:
                    # Échec ponctuel, attente courte (interruptible).
                    if self.stop_event.wait(self.config.RECONNECTION_SLEEP):
                        break
                continue

            # Frame lue avec succès, réinitialiser les compteurs
            self.frame_failures = 0
            self.reconnection_attempts = 0
            self._note_frame()   # santé : compteur + FPS

            frame = cv2.resize(frame, self.config.FRAME_SIZE)
            
            # Mettre la frame dans la queue
            if self.frame_queue.full():
                try:
                    self.frame_queue.get_nowait()
                except queue.Empty:
                    pass
            try:
                self.frame_queue.put_nowait(frame)
            except queue.Full:
                pass
        
        if self.cap:
            self.cap.release()
        logger.info(
            f"Thread de capture caméra {self.cam_id} arrêté",
            extra={'camera_id': self.cam_id}
        )

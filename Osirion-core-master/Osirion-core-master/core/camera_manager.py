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
    
    def handle_reconnection(self) -> bool:
        """Gère la reconnexion après des échecs. Retourne True si succès, False si abandon"""
        logger.warning(
            f"Caméra {self.cam_id} ({self.cam_name}) : {self.frame_failures} échecs consécutifs, reconnexion...",
            extra={'camera_id': self.cam_id, 'frame_failures': self.frame_failures}
        )
        
        # Libérer la connexion actuelle
        if self.cap:
            self.cap.release()
        
        # Calculer le délai avec backoff exponentiel
        delay = min(
            self.config.RECONNECTION_BASE_DELAY * (2 ** self.reconnection_attempts),
            self.config.MAX_RECONNECTION_DELAY
        )
        logger.info(
            f"Caméra {self.cam_id} : attente de {delay:.1f}s avant reconnexion "
            f"(tentative {self.reconnection_attempts + 1}/{self.config.MAX_RECONNECTION_ATTEMPTS})",
            extra={'camera_id': self.cam_id, 'delay': delay, 'attempt': self.reconnection_attempts + 1}
        )
        time.sleep(delay)
        
        # Tenter la reconnexion
        self.cap = self.connect_camera()
        
        if self.cap:
            logger.info(
                f"Caméra {self.cam_id} ({self.cam_name}) reconnectée avec succès",
                extra={'camera_id': self.cam_id}
            )
            self.reconnection_attempts = 0
            self.frame_failures = 0
            return True
        else:
            self.reconnection_attempts += 1
            if self.reconnection_attempts >= self.config.MAX_RECONNECTION_ATTEMPTS:
                logger.error(
                    f"Caméra {self.cam_id} : échec après {self.config.MAX_RECONNECTION_ATTEMPTS} tentatives, abandon",
                    extra={'camera_id': self.cam_id, 'attempts': self.config.MAX_RECONNECTION_ATTEMPTS}
                )
                return False
            return True
    
    def run(self):
        """Boucle principale de capture"""
        # Connexion initiale
        logger.info(
            f"Connexion à la caméra {self.cam_id} ({self.cam_name})...",
            extra={'camera_id': self.cam_id}
        )
        self.cap = self.connect_camera()
        if not self.cap:
            logger.error(
                f"Caméra {self.cam_id} ({self.cam_name}) : impossible d'ouvrir le flux RTSP",
                extra={'camera_id': self.cam_id, 'rtsp_url': _mask_rtsp_url(self.rtsp_url)}
            )
            return
        
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
                    if not self.handle_reconnection():
                        return  # Abandon définitif
                else:
                    # Échec ponctuel, attente courte
                    time.sleep(self.config.RECONNECTION_SLEEP)
                continue
            
            # Frame lue avec succès, réinitialiser les compteurs
            self.frame_failures = 0
            self.reconnection_attempts = 0
            
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

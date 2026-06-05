# core/surveillance_system.py
"""
Système de surveillance multi-caméras avec reconnaissance faciale
"""
import threading
import queue
import time
from typing import List, Dict

from ByteTrack.yolox.tracker.byte_tracker import BYTETracker
from services.camera_fetching_service import fetch_camera_list
from core.camera_manager import CameraCapture
from core.tracking_processor import TrackingProcessor
from core.global_person_tracker import GlobalPersonTracker
from core.runtime_control import RuntimeControl
from utils.logger import get_logger

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
        self.stop_event = threading.Event()
        
        # Tracker global multi-caméra
        # Fallback aligné sur l'échelle cosine IndexFlatIP (0.50 au lieu de l'ancien 0.75 sur (cosine+1)/2)
        self.global_tracker = GlobalPersonTracker(
            cache_ttl_seconds=getattr(config, 'GLOBAL_CACHE_TTL_SECONDS', 300),
            similarity_threshold=getattr(config, 'GLOBAL_SIMILARITY_THRESHOLD', 0.50)
        )

        # Contrôle runtime (toggle LPR depuis le frontend). Initialisé sur la valeur
        # de config, modifiable à chaud via l'endpoint Flask /api/lpr/toggle.
        self.runtime_control = RuntimeControl(
            lpr_enabled=getattr(config, 'ENABLE_PLATE_RECOGNITION', False)
        )
        
        self.threads = []
        self.web_server = None
    
    def initialize_cameras(self):
        """Charge et initialise les caméras actives"""
        cameras = fetch_camera_list()
        logger.info(f"Caméras trouvées au total : {len(cameras)}")

        # Filtrer uniquement les caméras actives
        self.active_cameras = [cam for cam in cameras if cam.get("is_active", False)]
        if not self.active_cameras:
            logger.warning("Aucune caméra active trouvée. Le système démarre sans caméra et attend.")
            return True

        active_cam_strs = [f"{cam['cam_name']} (id={cam['id']}, {cam['location']})"
                          for cam in self.active_cameras]
        logger.info(f"Caméras actives : {active_cam_strs}")
        return True
    
    def setup_camera_structures(self):
        """Initialise les structures de données pour chaque caméra"""
        for cam in self.active_cameras:
            cam_id = cam["id"]
            self.frame_queues[cam_id] = queue.Queue(maxsize=self.config.FRAME_QUEUE_MAXSIZE)
            self.result_frames[cam_id] = None
            self.result_metadata[cam_id] = None
            self.result_locks[cam_id] = threading.Lock()
            self.trackers[cam_id] = BYTETracker(
                self.config.BYTE_TRACK_ARGS,
                frame_rate=self.config.BYTE_TRACK_FRAME_RATE,
            )
            self.track_id_to_person[cam_id] = {}
            self.current_frame_idx[cam_id] = 0
    
    def start_camera_threads(self):
        """Démarre les threads de capture et de traitement pour chaque caméra"""
        for cam in self.active_cameras:
            cam_id = cam["id"]
            
            # Thread de capture RTSP
            capture = CameraCapture(
                cam=cam,
                frame_queue=self.frame_queues[cam_id],
                stop_event=self.stop_event,
                config=self.config
            )
            capture_thread = threading.Thread(target=capture.run, daemon=True)
            capture_thread.start()
            self.threads.append(capture_thread)
            
            # Thread de traitement
            processor = TrackingProcessor(
                cam=cam,
                frame_queue=self.frame_queues[cam_id],
                result_frames=self.result_frames,
                result_metadata=self.result_metadata,
                result_lock=self.result_locks[cam_id],
                tracker=self.trackers[cam_id],
                person_db=self.track_id_to_person[cam_id],
                frame_idx_container=self.current_frame_idx,
                stop_event=self.stop_event,
                config=self.config,
                global_tracker=self.global_tracker,  # Ajout du tracker global
                runtime_control=self.runtime_control  # Toggle LPR partagé
            )
            processing_thread = threading.Thread(target=processor.run, daemon=True)
            processing_thread.start()
            self.threads.append(processing_thread)
    
    def run(self):
        """Démarre le système de surveillance"""
        if not self.initialize_cameras():
            return False
        
        self.setup_camera_structures()
        self.start_camera_threads()
        
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
        self.stop_event.set()
        
        # Afficher les statistiques du tracker global
        stats = self.global_tracker.get_statistics()
        logger.info(
            f"Statistiques tracking global : {stats['active_persons']} personnes actives, "
            f"{stats['total_persons_tracked']} total suivies, "
            f"taux de cache hit : {stats['cache_hit_rate']}"
        )
        
        # Arrêter le serveur web si actif
        if self.web_server:
            self.web_server.stop()
        
        time.sleep(0.5)
        logger.info("Application multi-caméras fermée proprement")

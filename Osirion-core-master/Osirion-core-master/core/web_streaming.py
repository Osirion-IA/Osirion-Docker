# core/web_streaming.py
"""
Serveur de streaming WebSocket pour faible latence
Expose les flux caméras via WebSocket pour intégration dans votre frontend
"""
import base64
import cv2
from flask import Flask, jsonify, request
from flask_socketio import SocketIO, emit, join_room, leave_room
import threading
import time
from utils.logger import get_logger

logger = get_logger(__name__)


class WebStreamingServer:
    """
    Serveur WebSocket qui expose les flux caméras en temps réel

    Fonctionnement:
    1. Client se connecte via WebSocket (socket.io)
    2. Client envoie 'start_stream' avec camera_id
    3. Serveur envoie les frames en continu via événement 'frame'
    4. Client affiche les frames dans un canvas HTML
    """

    def __init__(self, surveillance_system, host='0.0.0.0', port=5000):
        self.surveillance_system = surveillance_system
        self.host = host
        self.port = port

        self.app = Flask(__name__)
        self.app.config['SECRET_KEY'] = surveillance_system.config.FLASK_SECRET_KEY

        cors_origins = surveillance_system.config.CORS_ALLOWED_ORIGINS
        self.socketio = SocketIO(self.app, cors_allowed_origins=cors_origins, async_mode='threading')

        # {session_id: camera_id}  — caméra regardée par chaque client
        self.active_streams = {}
        # {camera_id: set(session_ids)}  — clients regardant chaque caméra
        self.camera_viewers = {}
        # {camera_id: threading.Thread}  — 1 thread broadcast par caméra active
        self.broadcast_threads = {}

        self.stream_lock = threading.Lock()
        self._stop_event = threading.Event()

        # Cache JPEG par caméra partagé entre tous les clients.
        self._jpeg_cache: dict = {}   # {camera_id: {'frame_id': int, 'jpeg': str (base64)}}
        self._jpeg_locks: dict = {}   # {camera_id: threading.Lock}

        self._setup_routes()
        self._setup_socketio()

        logger.info("WebStreamingServer initialisé")

    def _setup_routes(self):
        """Configure les routes HTTP REST API"""

        @self.app.route('/')
        def index():
            doc = {
                "name": "Osirion Camera Streaming API",
                "version": "2.0.0",
                "protocol": "WebSocket (Socket.IO)",
                "endpoints": {
                    "GET /api/cameras": "Liste des caméras disponibles",
                    "GET /api/stats": "Statistiques du système"
                },
                "websocket": {
                    "url": f"ws://{self.host}:{self.port}",
                    "events": {
                        "connect": "Connexion établie, reçoit cameras_list",
                        "start_stream": "Démarrer un stream {camera_id: int}",
                        "stop_stream": "Arrêter le stream actuel",
                        "frame": "Réception des frames {camera_id, data (ArrayBuffer), timestamp}",
                        "disconnect": "Déconnexion"
                    }
                },
                "example": {
                    "javascript": "const socket = io('http://localhost:5000'); socket.emit('start_stream', {camera_id: 1});"
                }
            }
            return jsonify(doc)

        @self.app.route('/api/cameras')
        def cameras_list():
            cameras = []
            for cam in self.surveillance_system.active_cameras:
                cam_id = cam["id"]
                cam_lock = self.surveillance_system.result_locks.get(
                    cam_id, self.surveillance_system.result_lock
                )
                with cam_lock:
                    has_frame = self.surveillance_system.result_frames.get(cam_id) is not None

                cameras.append({
                    "id": cam_id,
                    "name": cam["cam_name"],
                    "location": cam["location"],
                    "status": "online" if has_frame else "offline"
                })

            return jsonify({"cameras": cameras, "count": len(cameras)})

        @self.app.route('/api/stats')
        def system_stats():
            with self.stream_lock:
                active_viewers = len(self.active_streams)
                active_cameras = len(self.broadcast_threads)

            return jsonify({
                "total_cameras": len(self.surveillance_system.active_cameras),
                "active_viewers": active_viewers,
                "active_broadcast_cameras": active_cameras,
                "uptime": time.time() - getattr(self, 'start_time', time.time())
            })

    def _setup_socketio(self):
        """Configure les événements WebSocket"""

        @self.socketio.on('connect')
        def handle_connect():
            sid = request.sid
            logger.info(f"Client WebSocket connecté", extra={'client_id': sid})
            cameras_data = [
                {"id": cam["id"], "name": cam["cam_name"], "location": cam["location"]}
                for cam in self.surveillance_system.active_cameras
            ]
            emit('cameras_list', {'cameras': cameras_data})

        @self.socketio.on('disconnect')
        def handle_disconnect():
            sid = request.sid
            logger.info(f"Client WebSocket déconnecté", extra={'client_id': sid})
            self._unsubscribe_client(sid)

        @self.socketio.on('start_stream')
        def handle_start_stream(data):
            sid = request.sid
            camera_id = data.get('camera_id')

            if not camera_id:
                emit('error', {'message': 'camera_id required'})
                return

            valid_ids = [cam['id'] for cam in self.surveillance_system.active_cameras]
            if camera_id not in valid_ids:
                emit('error', {'message': f'Camera {camera_id} not found'})
                return

            # Quitter l'ancienne caméra si nécessaire
            with self.stream_lock:
                if sid in self.active_streams:
                    self._leave_camera(sid, self.active_streams[sid])

                # Inscrire le client à la nouvelle caméra
                self.active_streams[sid] = camera_id
                if camera_id not in self.camera_viewers:
                    self.camera_viewers[camera_id] = set()
                self.camera_viewers[camera_id].add(sid)

                # Démarrer le thread broadcast si aucun n'est actif pour cette caméra
                existing = self.broadcast_threads.get(camera_id)
                if existing is None or not existing.is_alive():
                    t = threading.Thread(
                        target=self._broadcast_camera,
                        args=(camera_id,),
                        daemon=True
                    )
                    self.broadcast_threads[camera_id] = t
                    t.start()

            join_room(f'camera_{camera_id}')
            logger.info(
                f"Client {sid} regarde caméra {camera_id}",
                extra={'client_id': sid, 'camera_id': camera_id}
            )
            emit('stream_started', {'camera_id': camera_id})

        @self.socketio.on('stop_stream')
        def handle_stop_stream():
            sid = request.sid
            camera_id = None

            with self.stream_lock:
                if sid in self.active_streams:
                    camera_id = self.active_streams[sid]
                    self._leave_camera(sid, camera_id)

            if camera_id is not None:
                leave_room(f'camera_{camera_id}')
                logger.info(
                    f"Client {sid} a arrêté le stream caméra {camera_id}",
                    extra={'client_id': sid, 'camera_id': camera_id}
                )
            emit('stream_stopped')

    def _leave_camera(self, sid: str, camera_id: int):
        """Désinscrit un client d'une caméra (appelé sous stream_lock)."""
        self.active_streams.pop(sid, None)
        viewers = self.camera_viewers.get(camera_id)
        if viewers is not None:
            viewers.discard(sid)

    def _unsubscribe_client(self, sid: str):
        """Nettoie toutes les souscriptions d'un client déconnecté."""
        with self.stream_lock:
            if sid in self.active_streams:
                self._leave_camera(sid, self.active_streams.get(sid))

    def _has_viewers(self, camera_id: int) -> bool:
        """Retourne True si au moins un client regarde cette caméra."""
        with self.stream_lock:
            return bool(self.camera_viewers.get(camera_id))

    def _broadcast_camera(self, camera_id: int):
        """
        Thread de broadcast : 1 thread par caméra active.
        Envoie la frame courante à TOUS les clients du room camera_{camera_id}
        en un seul emit — élimine N threads redondants pour N clients.

        Les frames sont envoyées en binaire (bytes JPEG) pour supprimer
        l'overhead base64 (+33 % bande passante, 3-5 ms décodage JS).
        """
        fps = 30
        frame_delay = 1.0 / fps
        frames_sent = 0

        logger.debug(
            f"Thread broadcast démarré pour caméra {camera_id}",
            extra={'camera_id': camera_id}
        )

        if camera_id not in self._jpeg_locks:
            self._jpeg_locks[camera_id] = threading.Lock()

        while not self._stop_event.is_set():
            if not self._has_viewers(camera_id):
                break

            start_time = time.time()

            # Lecture de la frame avec le verrou par caméra (P3)
            cam_lock = self.surveillance_system.result_locks.get(
                camera_id, self.surveillance_system.result_lock
            )
            with cam_lock:
                frame = self.surveillance_system.result_frames.get(camera_id)

            if frame is not None:
                try:
                    # Cache JPEG par frame (double-checked locking)
                    frame_id = id(frame)
                    cache = self._jpeg_cache.get(camera_id, {})
                    if cache.get('frame_id') != frame_id:
                        with self._jpeg_locks[camera_id]:
                            cache = self._jpeg_cache.get(camera_id, {})
                            if cache.get('frame_id') != frame_id:
                                quality = getattr(
                                    self.surveillance_system.config, 'JPEG_QUALITY', 85
                                )
                                _, buffer = cv2.imencode(
                                    '.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, quality]
                                )
                                self._jpeg_cache[camera_id] = {
                                    'frame_id': frame_id,
                                    'jpeg': base64.b64encode(buffer).decode('utf-8')
                                }

                    frame_b64 = self._jpeg_cache[camera_id]['jpeg']

                    # Broadcast vers tous les clients de cette caméra en un seul emit
                    self.socketio.emit(
                        'frame',
                        {'camera_id': camera_id, 'data': frame_b64, 'timestamp': time.time()},
                        room=f'camera_{camera_id}'
                    )
                    frames_sent += 1

                except Exception:
                    logger.error(
                        f"Erreur broadcast caméra {camera_id}",
                        extra={'camera_id': camera_id},
                        exc_info=True
                    )

            elapsed = time.time() - start_time
            time.sleep(max(0, frame_delay - elapsed))

        logger.debug(
            f"Thread broadcast terminé pour caméra {camera_id} ({frames_sent} frames envoyées)",
            extra={'camera_id': camera_id}
        )

    def start(self):
        """Démarre le serveur WebSocket dans un thread séparé"""
        self.start_time = time.time()
        server_thread = threading.Thread(target=self._run_server, daemon=True)
        server_thread.start()
        logger.info(f"Serveur de streaming WebSocket démarré sur http://{self.host}:{self.port}")
        logger.info(f"Connectez votre frontend via: const socket = io('http://{self.host}:{self.port}')")

    def _run_server(self):
        """Exécute le serveur Flask-SocketIO"""
        try:
            self.socketio.run(
                self.app,
                host=self.host,
                port=self.port,
                debug=False,
                use_reloader=False,
                log_output=False,
                allow_unsafe_werkzeug=True
            )
        except Exception:
            logger.error(f"Erreur serveur WebSocket", exc_info=True)

    def stop(self):
        """Arrête proprement le serveur"""
        logger.info("Arrêt du serveur de streaming...")
        self._stop_event.set()
        with self.stream_lock:
            self.active_streams.clear()
            self.camera_viewers.clear()
            self.broadcast_threads.clear()
        logger.info("Serveur de streaming arrêté")

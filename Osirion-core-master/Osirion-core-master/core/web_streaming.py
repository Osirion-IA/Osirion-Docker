# core/web_streaming.py
"""
Serveur de métadonnées temps réel (Socket.IO) — architecture VMS Phase 2.

Le Core n'envoie PLUS d'images : la vidéo est servie en WebRTC par MediaMTX,
directement au navigateur. Ce serveur ne diffuse que des bounding boxes JSON
(événement 'metadata') que le frontend superpose sur la vidéo via un <canvas>.
"""
import sys
from flask import Flask, jsonify, request
from flask_socketio import SocketIO, emit, join_room, leave_room
import threading
import time
from utils.logger import get_logger
from utils.measurement import get_measurement

# flask_cors est optionnel : autorise le navigateur (frontend) à appeler les
# routes REST /api/* du Core (ex. toggle facial). Sans lui, le toggle même-origine
# fonctionne quand même via le proxy Next.js — donc import non bloquant.
try:
    from flask_cors import CORS
    _HAS_CORS = True
except Exception:
    CORS = None
    _HAS_CORS = False

logger = get_logger(__name__)


class WebStreamingServer:
    """
    Serveur WebSocket qui expose les métadonnées (bounding boxes) en temps réel

    Fonctionnement:
    1. Client se connecte via WebSocket (socket.io)
    2. Client envoie 'start_stream' avec camera_id
    3. Serveur envoie en continu les détections via événement 'metadata'
    4. La vidéo, elle, est lue séparément en WebRTC depuis MediaMTX
    5. Le client dessine les boxes sur un <canvas> superposé à la <video>
    """

    def __init__(self, surveillance_system, host='0.0.0.0', port=5000):
        self.surveillance_system = surveillance_system
        self.host = host
        self.port = port

        self.app = Flask(__name__)
        self.app.config['SECRET_KEY'] = surveillance_system.config.FLASK_SECRET_KEY

        cors_origins = surveillance_system.config.CORS_ALLOWED_ORIGINS
        self.socketio = SocketIO(self.app, cors_allowed_origins=cors_origins, async_mode='threading')

        # CORS sur les routes REST /api/* (toggles appelés par le navigateur).
        # supports_credentials=True → Flask-CORS reflète l'Origin autorisée au lieu
        # d'un '*' littéral (cohérent avec le Socket.IO, robuste si un fetch envoie
        # des credentials).
        if _HAS_CORS:
            CORS(self.app, resources={r"/api/*": {"origins": cors_origins}},
                 supports_credentials=True)

        # {session_id: camera_id}  — caméra regardée par chaque client
        self.active_streams = {}
        # {camera_id: set(session_ids)}  — clients regardant chaque caméra
        self.camera_viewers = {}
        # {camera_id: threading.Thread}  — 1 thread broadcast par caméra active
        self.broadcast_threads = {}

        self.stream_lock = threading.Lock()
        self._stop_event = threading.Event()

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
                        "start_stream": "S'abonner aux métadonnées d'une caméra {camera_id: int}",
                        "stop_stream": "Se désabonner",
                        "metadata": "Détections {camera_id, width, height, detections:[{type, bbox:[x1,y1,x2,y2], label, track_id}]}",
                        "disconnect": "Déconnexion"
                    },
                    "note": "La vidéo est servie séparément en WebRTC (WHEP) par MediaMTX."
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
                    has_meta = self.surveillance_system.result_metadata.get(cam_id) is not None

                cameras.append({
                    "id": cam_id,
                    "name": cam["cam_name"],
                    "location": cam["location"],
                    "status": "online" if has_meta else "offline"
                })

            return jsonify({"cameras": cameras, "count": len(cameras)})

        @self.app.route('/api/cameras/health')
        def cameras_health():
            """Santé temps réel par caméra (état, FPS, reconnexions, viewers…)."""
            try:
                cams = self.surveillance_system.camera_health()
            except Exception:
                logger.error("Erreur lors du calcul de la santé des caméras", exc_info=True)
                cams = []
            # Enrichir avec le nb de clients qui regardent (info propre au serveur web).
            with self.stream_lock:
                viewers = {cid: len(s) for cid, s in self.camera_viewers.items()}
            for c in cams:
                c["viewers"] = viewers.get(c["id"], 0)
            return jsonify({
                "cameras": cams,
                "count": len(cams),
                "online": sum(1 for c in cams if c.get("state") == "online"),
                "server_time": time.time(),
            })

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

        # ── GPU — métriques d'utilisation (si NVIDIA disponible) ───────────────
        @self.app.route('/api/gpu')
        def gpu_stats():
            from utils.gpu_monitor import get_gpu_stats
            return jsonify(get_gpu_stats())

        # ── MESURE (chapitre 4) — pilotage de campagne via localhost (hors-ligne)
        # Permet de marquer les scénarios et de poser la vérité terrain sans
        # internet : tout est journalisé dans metrics.jsonl (cf. utils/measurement).
        @self.app.route('/api/measure/status')
        def measure_status():
            return jsonify(get_measurement().status())

        @self.app.route('/api/measure/mark', methods=['POST'])
        def measure_mark():
            data = request.get_json(silent=True) or {}
            label = data.get('label') or request.args.get('label')
            get_measurement().mark(label)
            return jsonify({"ok": True, "scenario": label})

        @self.app.route('/api/measure/expect', methods=['POST'])
        def measure_expect():
            """Vérité terrain visage : {camera_id:int, person:str}. person vide = efface."""
            data = request.get_json(silent=True) or {}
            cam_raw = data.get('camera_id', request.args.get('camera_id'))
            person = data.get('person', request.args.get('person'))
            try:
                camera_id = int(cam_raw)
            except (TypeError, ValueError):
                return jsonify({"error": "camera_id (int) requis"}), 400
            get_measurement().set_expected(camera_id, person)
            return jsonify({"ok": True, "camera_id": camera_id, "expected": person or None})

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
        Diffuse les métadonnées (bounding boxes JSON) à TOUS les clients du room
        camera_{camera_id} en un seul emit. Aucune image, aucun encodage : le Core
        ne touche plus au transport vidéo (assuré par MediaMTX en WebRTC).

        On déduplique par `seq` (= frame_idx) : on n'émet que lorsque le payload a
        réellement changé → ~10 emits/s (cadence d'inférence) au lieu de 30.
        """
        poll_fps = 30
        poll_delay = 1.0 / poll_fps
        sent = 0
        last_seq = None

        logger.debug(
            f"Thread broadcast (metadata) démarré pour caméra {camera_id}",
            extra={'camera_id': camera_id}
        )

        while not self._stop_event.is_set():
            if not self._has_viewers(camera_id):
                break

            start_time = time.time()

            # Lecture du dernier payload avec le verrou par caméra
            cam_lock = self.surveillance_system.result_locks.get(
                camera_id, self.surveillance_system.result_lock
            )
            with cam_lock:
                meta = self.surveillance_system.result_metadata.get(camera_id)

            if meta is not None and meta.get('seq') != last_seq:
                try:
                    last_seq = meta['seq']
                    self.socketio.emit(
                        'metadata',
                        meta['payload'],
                        room=f'camera_{camera_id}'
                    )
                    sent += 1
                except Exception:
                    logger.error(
                        f"Erreur broadcast metadata caméra {camera_id}",
                        extra={'camera_id': camera_id},
                        exc_info=True
                    )

            elapsed = time.time() - start_time
            time.sleep(max(0, poll_delay - elapsed))

        logger.debug(
            f"Thread broadcast terminé pour caméra {camera_id} ({sent} payloads envoyés)",
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
        # Serveur de dev Werkzeug ASSUMÉ pour le flux Socket.IO (léger, 1 endpoint) :
        # allow_unsafe_werkzeug=True est déjà posé. On coupe l'avertissement
        # « production deployment » du logger werkzeug (bruit, choix conscient).
        import logging as _logging
        _logging.getLogger("werkzeug").setLevel(_logging.ERROR)
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

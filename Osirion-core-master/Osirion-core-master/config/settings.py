# config/settings.py
"""
Configuration centralisée du Core (Vision Engine anonyme : détection de personnes).
"""

import os
import secrets
import types as _types
from dotenv import load_dotenv

load_dotenv()

# ----------------------
# Configuration des frames
# ----------------------
# Résolution de TRAITEMENT (détection de personnes YOLO). La vidéo AFFICHÉE
# (WebRTC servie par MediaMTX) est indépendante de cette valeur : la monter
# n'augmente QUE la qualité de détection et le coût GPU, jamais le débit vidéo
# navigateur. Dialer selon le budget GPU (↔ nombre de caméras) : 960×540 ou
# 640×480 pour alléger. Ordre (largeur, hauteur) — attendu par cv2.resize.
FRAME_WIDTH = int(os.getenv('FRAME_WIDTH', '1280'))
FRAME_HEIGHT = int(os.getenv('FRAME_HEIGHT', '720'))
FRAME_SIZE = (FRAME_WIDTH, FRAME_HEIGHT)
PROCESS_EVERY_N_FRAME = 3         # 1 frame sur N traitée (allège le GPU à N caméras)
FRAME_QUEUE_MAXSIZE = 4           # Buffer pour absorber les pics GPU
FRAME_QUEUE_TIMEOUT = 0.1         # Timeout de récupération d'une frame (secondes)

# ----------------------
# Configuration du tracker — OC-SORT (Observation-Centric SORT)
# ----------------------
# Implémentation AUTONOME (core/trackers/oc_sort.py) ; l'adaptateur
# OCSortTrackerAdapter préserve l'API update(dets, img_info, img_size).
OC_SORT_ARGS = _types.SimpleNamespace(
    det_thresh=0.4,       # Seuil des détections haute confiance
    max_age=30,           # Frames avant suppression d'un track perdu
    iou_threshold=0.3,    # Seuil d'association IoU
    delta_t=3,            # Fenêtre de look-back pour l'estimation de vitesse
    inertia=0.2,          # Poids du terme d'inertie/momentum (OCM)
    use_byte=True,        # Récupération BYTE des détections faibles
)

# ----------------------
# Détection de personnes (SEULE couche GPU — Vision Engine anonyme)
# ----------------------
# Modèle YOLO (COCO classe 0 « person »), défaut yolo26n (NMS-free, edge-optimisé).
# Le nom/chemin et la demi-précision sont aussi lus par person_detection.py
# (PERSON_MODEL_PATH, PERSON_YOLO_HALF). Ici : le seuil de confiance minimal.
PERSON_MODEL_PATH = os.getenv('PERSON_MODEL_PATH', 'yolo26n.pt')
PERSON_DETECTION_CONFIDENCE = float(os.getenv('PERSON_DETECTION_CONFIDENCE', '0.4'))
PERSON_YOLO_HALF = os.getenv('PERSON_YOLO_HALF', 'true').lower() == 'true'

# Filtre qualité frame : variance de la transformée de Laplace sur la luminance.
# Une frame trop floue (< seuil) est sautée (pas d'inférence, overlay conservé).
#   < 40 très flou · 40-80 flou modéré · > 80 acceptable · > 200 net.
# 0 = filtre désactivé (caméra fixe haute qualité / debug).
BLUR_THRESHOLD = float(os.getenv('BLUR_THRESHOLD', '80.0'))

# ----------------------
# Event Engine (occupation / attroupement / comptage) — Phase C
# ----------------------
# Rafraîchissement (s) des zones/lignes depuis le backend, dans un thread dédié
# (jamais sur le thread caméra).
ZONES_REFRESH_SECONDS = int(os.getenv('ZONES_REFRESH_SECONDS', '30'))
# Attroupement : l'occupation doit rester ≥ seuil pendant N secondes avant
# d'émettre CROWD_DETECTED (anti-faux-positif sur pic bref).
CROWD_MIN_SECONDS = float(os.getenv('CROWD_MIN_SECONDS', '3.0'))
# Throttle des ZONE_OCCUPANCY_CHANGED : au plus un par zone toutes les N secondes
# (borne les écritures DB).
OCCUPANCY_EMIT_INTERVAL = float(os.getenv('OCCUPANCY_EMIT_INTERVAL', '2.0'))
# Temps de présence minimal (s) pour émettre un ZONE_DWELL (filtre les passages éclairs).
DWELL_MIN_SECONDS = float(os.getenv('DWELL_MIN_SECONDS', '1.0'))

# ----------------------
# Configuration de la reconnexion RTSP
# ----------------------
RECONNECTION_SLEEP = 0.1          # Délai avant tentative de reconnexion RTSP (s)
MAX_RECONNECTION_ATTEMPTS = 5     # Tentatives avant d'escalader le log en ERROR (la reconnexion ne s'arrête JAMAIS)
RECONNECTION_BASE_DELAY = 1.0     # Délai de base du backoff exponentiel (s)
MAX_RECONNECTION_DELAY = 30.0     # Délai maximum entre tentatives (s)
FRAME_FAILURE_THRESHOLD = 10      # Échecs consécutifs avant de déclencher une reconnexion

# ----------------------
# Supervision des caméras à chaud (hot-add / hot-remove)
# ----------------------
# Intervalle (s) du thread de supervision : le Core ré-interroge la liste des
# caméras du backend et applique les changements À CHAUD (ajout, (dé)activation,
# suppression, redémarrage d'un thread mort). 0 = supervision désactivée.
CAMERA_REFRESH_SECONDS = int(os.getenv('CAMERA_REFRESH_SECONDS', '15'))

# ----------------------
# Dispositif de MESURE (évaluation du chapitre 4 du mémoire)
# ----------------------
# Le Core journalise des métriques hors-ligne (latence, débit, GPU) dans un fichier
# JSON Lines (MEASURE_FILE), dépouillé par tools/analyze_metrics.py. Activation/
# fichier lus par utils.measurement. Ici : intervalle d'échantillonnage système (s).
MEASURE_SAMPLE_SECONDS = int(os.getenv('MEASURE_SAMPLE_SECONDS', '5'))

# ----------------------
# Source de capture vidéo (architecture VMS — Phase 2)
# ----------------------
# READ_FROM_MEDIAMTX=true : le Core lit le flux RTSP REPUBLIÉ par MediaMTX
# (rtsp://<base>/cam<id>) → UNE seule connexion à la caméra physique, partagée
# entre l'IA (Core) et la vidéo navigateur (WebRTC). false = Core ouvre rtsp_url.
READ_FROM_MEDIAMTX = os.getenv('READ_FROM_MEDIAMTX', 'false').lower() == 'true'
MEDIAMTX_RTSP_BASE = os.getenv('MEDIAMTX_RTSP_BASE', 'mediamtx:8554')  # hôte:port RTSP interne

# ----------------------
# Chemins MediaMTX dynamiques (1 par caméra) — voir services.mediamtx_path_service
# ----------------------
# Le Core crée/met à jour/supprime à chaud le chemin `cam<id>` via l'API HTTP de
# MediaMTX, à partir du rtsp_url du backend (source à la demande).
MANAGE_MEDIAMTX_PATHS = os.getenv('MANAGE_MEDIAMTX_PATHS', 'true').lower() == 'true'
MEDIAMTX_API_BASE = os.getenv('MEDIAMTX_API_BASE', 'http://mediamtx:9997')
MEDIAMTX_RTSP_TRANSPORT = os.getenv('MEDIAMTX_RTSP_TRANSPORT', 'tcp')     # tcp = pas de perte RTP
MEDIAMTX_ON_DEMAND_CLOSE_AFTER = os.getenv('MEDIAMTX_ON_DEMAND_CLOSE_AFTER', '30s')

# ----------------------
# Configuration du streaming web
# ----------------------
ENABLE_WEB_STREAMING = True       # Serveur Flask + Socket.IO (métadonnées overlay)
WEB_STREAMING_HOST = '0.0.0.0'    # Interface réseau (0.0.0.0 = toutes)
WEB_STREAMING_PORT = 5000         # Port du serveur web
JPEG_QUALITY = 85                 # (héritage) qualité JPEG — plus utilisé en Phase 2

# ----------------------
# Configuration de sécurité (CORS / session Flask)
# ----------------------
# Secret Flask pour signer les sessions (CRITIQUE : NE JAMAIS hardcoder).
FLASK_SECRET_KEY = os.getenv('FLASK_SECRET_KEY', secrets.token_hex(32))

# Mode d'exécution : OSIRION_ENV = 'development' (défaut) | 'production'.
#   • development : CORS ouvert (origine reflétée → compatible withCredentials).
#   • production  : CORS limité à CORS_ALLOWED_ORIGINS (wildcard interdit).
ENV = os.getenv('OSIRION_ENV', 'development').strip().lower()
IS_PRODUCTION = ENV == 'production'

_cors_raw = os.getenv('CORS_ALLOWED_ORIGINS', '').strip()
if IS_PRODUCTION:
    _origins = [o.strip() for o in _cors_raw.split(',')
                if o.strip() and o.strip() != '*']
    if not _origins:
        raise RuntimeError(
            "OSIRION_ENV=production exige CORS_ALLOWED_ORIGINS avec des origines "
            "explicites (ex. https://vms.example.com). Le wildcard '*' est interdit "
            "en production (risque de fuite vidéo)."
        )
    CORS_ALLOWED_ORIGINS = _origins
elif _cors_raw and _cors_raw != '*':
    CORS_ALLOWED_ORIGINS = [o.strip() for o in _cors_raw.split(',') if o.strip()]
else:
    CORS_ALLOWED_ORIGINS = ['*']

# ----------------------
# Configuration du logging
# ----------------------
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')        # DEBUG, INFO, WARNING, ERROR, CRITICAL
LOG_DIR = os.getenv('LOG_DIR', 'logs')            # Répertoire des fichiers de logs
ENABLE_JSON_LOGS = os.getenv('ENABLE_JSON_LOGS', 'false').lower() == 'true'
ENABLE_CONSOLE_LOGS = os.getenv('ENABLE_CONSOLE_LOGS', 'true').lower() == 'true'
LOG_MAX_BYTES = int(os.getenv('LOG_MAX_BYTES', str(10 * 1024 * 1024)))  # 10 MB
LOG_BACKUP_COUNT = int(os.getenv('LOG_BACKUP_COUNT', '5'))

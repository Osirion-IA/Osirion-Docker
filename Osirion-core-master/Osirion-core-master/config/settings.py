# config/settings.py
"""
Configuration centralisée de l'application de surveillance multi-caméras
"""

import os
import secrets
from dotenv import load_dotenv

load_dotenv()

# ----------------------
# Configuration des frames
# ----------------------
FRAME_SIZE = (640, 480)           # Taille de chaque flux individuel
PROCESS_EVERY_N_FRAME = 3         # GPU RTX 4050 : 1 frame sur 3 (~10 FPS effectifs vs 3 FPS CPU)
FRAME_QUEUE_MAXSIZE = 4           # Buffer légèrement plus grand pour absorber les pics GPU
FRAME_QUEUE_TIMEOUT = 0.1         # Timeout pour récupérer une frame de la queue (secondes)

# ----------------------
# Configuration du ByteTrack
# ----------------------
_EFFECTIVE_FPS = 30 // PROCESS_EVERY_N_FRAME   # FPS réel du pipeline = 10

# BYTETracker attend un objet namespace (args) + frame_rate séparé
import types as _types
BYTE_TRACK_ARGS = _types.SimpleNamespace(
    track_thresh=0.5,
    track_buffer=_EFFECTIVE_FPS * 1,   # 10 — garde un track perdu ~1s à 10fps réels
    match_thresh=0.8,
    mot20=False,
)
BYTE_TRACK_FRAME_RATE = _EFFECTIVE_FPS

# ----------------------
# Configuration de la reconnaissance faciale
# ----------------------
FACE_DETECTION_CONFIDENCE = 0.7   # Seuil de confiance pour la détection de visages

# Filtre qualité frame : variance de la transformée de Laplace sur la luminance
# Références empiriques (frame 640×480 RTSP H.264) :
#   < 40  → très flou (caméra en mouvement, obturateur lent)
#   40-80 → flou modéré (sujet en mouvement rapide)
#   > 80  → acceptable pour ArcFace
#   > 200 → net (conditions idéales)
# 0 = filtre désactivé (utile en debug ou caméra fixe haute qualité)
BLUR_THRESHOLD = float(os.getenv('BLUR_THRESHOLD', '80.0'))

# Seuils recalibrés pour IndexFlatIP (cosine similarity directe ∈ [0, 1])
# Avant (IndexFlatL2 + 1/(1+L2)) : range utile [0.41, 0.70] → seuils 0.18/0.30 hors range
# Après (IndexFlatIP + cosine)    : range utile [0.05, 0.95] → seuils cohérents avec ArcFace buffalo_l
#   - même personne (live RTSP)    : cosine ≈ 0.45–0.80
#   - personnes différentes        : cosine ≈ 0.02–0.35
RECOGNITION_THRESHOLD = 0.45      # seuil initial — frontière match/non-match buffalo_l
ADAPTIVE_THRESHOLD_FLOOR = 0.35   # plancher absolu — en dessous = non-match garanti
ADAPTIVE_THRESHOLD_CEILING = 0.80 # plafond absolu — cohérent avec max cosine live (~0.85)
REIDENTIFICATION_INTERVAL = 200   # Frames avant de ré-identifier un track existant
CACHE_TTL_FRAMES = 600            # Durée de vie des tracks en cache (en frames)

# ----------------------
# Configuration de la reconnexion RTSP
# ----------------------
RECONNECTION_SLEEP = 0.1          # Délai avant tentative de reconnexion RTSP (secondes)
MAX_RECONNECTION_ATTEMPTS = 5     # Nombre maximum de tentatives de reconnexion avant abandon
RECONNECTION_BASE_DELAY = 1.0     # Délai de base pour le backoff exponentiel (secondes)
MAX_RECONNECTION_DELAY = 30.0     # Délai maximum entre les tentatives de reconnexion (secondes)
FRAME_FAILURE_THRESHOLD = 10      # Nombre d'échecs consécutifs avant de déclencher une reconnexion

# ----------------------
# Constantes de couleurs (BGR format)
# ----------------------
COLOR_UNKNOWN = (0, 0, 255)       # Rouge pour les visages inconnus
COLOR_RECOGNIZED = (0, 255, 0)    # Vert pour les visages reconnus
COLOR_TEXT_BG = (0, 0, 0)         # Noir pour le fond du texte
COLOR_TEXT_FG = (255, 255, 255)   # Blanc pour le texte

# ----------------------
# Configuration du streaming web
# ----------------------
ENABLE_WEB_STREAMING = True       # Activer/désactiver le streaming web
WEB_STREAMING_HOST = '0.0.0.0'    # Interface réseau (0.0.0.0 = toutes)
WEB_STREAMING_PORT = 5000         # Port du serveur web
JPEG_QUALITY = 85                 # Qualité JPEG pour le streaming (50-100)

# ----------------------
# Configuration de sécurité WebSocket
# ----------------------

# Secret Flask pour signer les sessions (CRITIQUE : NE JAMAIS hardcoder)
FLASK_SECRET_KEY = os.getenv('FLASK_SECRET_KEY', secrets.token_hex(32))

# CORS : origines autorisées pour les connexions WebSocket.
# En production : définir CORS_ALLOWED_ORIGINS dans .env avec les IPs/domaines exacts.
# Format : "http://192.168.1.10:3000,https://dashboard.example.com"
# ⚠️  '*' = wildcard — accepté UNIQUEMENT en développement local.
#     En production vidéosurveillance, le wildcard permet à n'importe quel
#     navigateur de se connecter au flux — risque de leak vidéo.
_cors_raw = os.getenv('CORS_ALLOWED_ORIGINS', '')
if not _cors_raw or _cors_raw.strip() == '*':
    import warnings
    if not os.getenv('OSIRION_DEV_MODE'):
        warnings.warn(
            "CORS_ALLOWED_ORIGINS non défini ou '*' — "
            "restreindre aux origines connues en production "
            "(définir CORS_ALLOWED_ORIGINS dans .env).",
            stacklevel=1
        )
    CORS_ALLOWED_ORIGINS = ['*']   # dev fallback explicite
else:
    CORS_ALLOWED_ORIGINS = [o.strip() for o in _cors_raw.split(',') if o.strip()]

# ----------------------
# Configuration du logging
# ----------------------
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')        # DEBUG, INFO, WARNING, ERROR, CRITICAL
LOG_DIR = os.getenv('LOG_DIR', 'logs')            # Répertoire des fichiers de logs
ENABLE_JSON_LOGS = os.getenv('ENABLE_JSON_LOGS', 'false').lower() == 'true'  # Logs JSON structurés
ENABLE_CONSOLE_LOGS = os.getenv('ENABLE_CONSOLE_LOGS', 'true').lower() == 'true'  # Affichage console
LOG_MAX_BYTES = int(os.getenv('LOG_MAX_BYTES', str(10 * 1024 * 1024)))  # 10 MB par défaut
LOG_BACKUP_COUNT = int(os.getenv('LOG_BACKUP_COUNT', '5'))  # 5 fichiers de backup

# ----------------------
# Configuration du tracking multi-caméra global
# ----------------------
GLOBAL_CACHE_TTL_SECONDS = int(os.getenv('GLOBAL_CACHE_TTL_SECONDS', '300'))  # 5 minutes par défaut
# Recalibré : était 0.75 sur échelle (cosine+1)/2 = cosine brut 0.50 ; maintenant cosine direct
GLOBAL_SIMILARITY_THRESHOLD = float(os.getenv('GLOBAL_SIMILARITY_THRESHOLD', '0.50'))  # cosine brut ∈ [0,1]
# -----------------------------------------
# configuration des événements (ex: reconnaissance, entrée/sortie)
# -----------------------------------------

EVENTS = ["RECOGNITION","ENTRY","EXIT","DETECTION","PLATE_RECOGNITION"]  # Types d'événements à créer

# -----------------------------------------
# Module LPR / ANPR — reconnaissance des plaques d'immatriculation
# -----------------------------------------
# Activation OPT-IN : désactivé par défaut pour ne JAMAIS perturber le pipeline
# facial existant. Pilotable au runtime via l'API du Core (/api/lpr/toggle),
# elle-même branchée sur l'interrupteur du frontend (page Paramètres).
ENABLE_PLATE_RECOGNITION = os.getenv('ENABLE_PLATE_RECOGNITION', 'false').lower() == 'true'

# Chemin du modèle YOLO de détection de plaque (poids .pt Ultralytics).
# Si le fichier est absent ou les libs (ultralytics/easyocr) manquantes,
# le module se désactive proprement (log d'avertissement) sans casser le facial.
PLATE_MODEL_PATH = os.getenv('PLATE_MODEL_PATH', 'license_plate_detector.pt')

# Seuils de détection / OCR
PLATE_DETECTION_CONFIDENCE = float(os.getenv('PLATE_DETECTION_CONFIDENCE', '0.45'))  # confiance YOLO mini
PLATE_OCR_MIN_CONFIDENCE = float(os.getenv('PLATE_OCR_MIN_CONFIDENCE', '0.40'))      # confiance OCR mini pour accepter une lecture
PLATE_OCR_GOOD_CONFIDENCE = float(os.getenv('PLATE_OCR_GOOD_CONFIDENCE', '0.65'))    # au-delà → lecture "définitive", OCR figé pour ce track

# Frame-skipping OCR : nb max de tentatives OCR par track avant de figer la lecture
PLATE_OCR_MAX_ATTEMPTS = int(os.getenv('PLATE_OCR_MAX_ATTEMPTS', '5'))

# Langues EasyOCR (les plaques étant alphanumériques latines, 'en' suffit)
PLATE_OCR_LANGS = [s.strip() for s in os.getenv('PLATE_OCR_LANGS', 'en').split(',') if s.strip()]

# Liste blanche de caractères autorisés sur une plaque (filtre l'OCR)
PLATE_OCR_ALLOWLIST = os.getenv('PLATE_OCR_ALLOWLIST', 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789')

# Longueur plausible d'une plaque (filtre les faux positifs OCR)
PLATE_MIN_CHARS = int(os.getenv('PLATE_MIN_CHARS', '4'))
PLATE_MAX_CHARS = int(os.getenv('PLATE_MAX_CHARS', '10'))

# Seuil de similarité pour la recherche floue côté backend (/plates/search)
PLATE_SEARCH_THRESHOLD = float(os.getenv('PLATE_SEARCH_THRESHOLD', '0.82'))

# Durée de vie (en frames) d'une plaque en cache de track avant nettoyage
PLATE_CACHE_TTL_FRAMES = int(os.getenv('PLATE_CACHE_TTL_FRAMES', '600'))

# Couleurs d'annotation des plaques (BGR) — distinctes des visages (vert/rouge)
COLOR_PLATE = (0, 200, 255)            # Jaune/orangé : plaque détectée/lue
COLOR_PLATE_BLACKLIST = (0, 0, 255)    # Rouge : plaque blacklistée (alerte)
COLOR_PLATE_KNOWN = (255, 200, 0)      # Bleu clair : plaque connue (non blacklistée)
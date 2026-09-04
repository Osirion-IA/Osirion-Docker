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
FRAME_QUEUE_MAXSIZE = 4           # Buffer pour absorber les pics GPU
FRAME_QUEUE_TIMEOUT = 0.1         # Timeout de récupération d'une frame (secondes)
# Fréquence de propagation de la santé vidéo vers les décisions métier. Elle est
# volontairement plus courte que le rafraîchissement de configuration caméra.
CAMERA_HEALTH_DECISION_INTERVAL = max(
    0.5, float(os.getenv('CAMERA_HEALTH_DECISION_INTERVAL', '2.0'))
)

# ----------------------
# Configuration du tracker — OC-SORT (Observation-Centric SORT)
# ----------------------
# Implémentation AUTONOME (core/trackers/oc_sort.py) ; l'adaptateur
# OCSortTrackerAdapter préserve l'API update(dets, img_info, img_size).
OC_SORT_ARGS = _types.SimpleNamespace(
    # Seuil des détections HAUTE confiance : crée/associe les tracks. Aligné sur
    # PERSON_DETECTION_CONFIDENCE (même env) → cohérent avec ce que YOLO produit.
    # Les détections ENTRE PERSON_TRACK_MIN_CONFIDENCE et ce seuil ne créent pas de
    # track mais servent à MAINTENIR les tracks occlus (récupération BYTE, ci-dessous).
    det_thresh=float(os.getenv('PERSON_DETECTION_CONFIDENCE', '0.4')),
    max_age=30,           # Frames avant suppression d'un track perdu
    iou_threshold=0.3,    # Seuil d'association IoU
    delta_t=3,            # Fenêtre de look-back pour l'estimation de vitesse
    inertia=0.2,          # Poids du terme d'inertie/momentum (OCM)
    use_byte=True,        # Récupération BYTE des détections faibles
    # Plancher des détections FAIBLES exploitées par BYTE. DOIT valoir le seuil
    # envoyé au détecteur (PERSON_TRACK_MIN_CONFIDENCE) : sinon les boîtes sous ce
    # plancher sont calculées par YOLO puis jetées par le tracker (réglage sans effet).
    low_thresh=float(os.getenv('PERSON_TRACK_MIN_CONFIDENCE', '0.1')),
    # Sursis de publication : un track confirmé mais non apparié reste publié
    # pendant N frames à sa DERNIÈRE POSITION OBSERVÉE (drapeau `predicted`).
    # Sans lui, une occlusion d'UNE frame retirait la personne du Scene Model
    # pendant 3 frames (le tracker exigeait à nouveau min_hits appariements) →
    # occupation clignotante et franchissements perdus. 0 = comportement historique.
    max_coast=int(os.getenv('TRACK_COAST_FRAMES', '8')),
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
# Plancher de confiance des détections ENVOYÉES AU TRACKER (bien plus bas que
# PERSON_DETECTION_CONFIDENCE). Objectif : nourrir la récupération BYTE d'OC-SORT,
# conçue pour MAINTENIR un track occlus grâce aux détections faibles (0.1–seuil).
# Sans ce plancher bas, BYTE est « à jeun » et une personne masquée 1–2 s disparaît
# du comptage (sous-comptage des files). Ces détections faibles ne CRÉENT jamais de
# track (réservé au seuil haut) → gain de recall sans explosion de faux positifs.
PERSON_TRACK_MIN_CONFIDENCE = float(os.getenv('PERSON_TRACK_MIN_CONFIDENCE', '0.1'))
# Résolution d'INFÉRENCE YOLO (côté long, letterbox). Vide/0 = défaut Ultralytics
# (640) → rétro-compatible. La monter (960, 1280…) augmente fortement le recall sur
# les personnes petites/lointaines (fond de file), au prix d'un coût GPU ~quadratique
# en la résolution. À arbitrer selon le budget GPU (↔ nombre de caméras actives).
PERSON_YOLO_IMGSZ = int(os.getenv('PERSON_YOLO_IMGSZ', '0')) or None


def _parse_imgsz_sequence(raw: str):
    """Liste d'échelles YOLO positives, ex. ``"640,960"``."""
    values = []
    for item in str(raw or "").split(","):
        try:
            value = int(item.strip())
        except (TypeError, ValueError):
            continue
        if value > 0 and value not in values:
            values.append(value)
    return tuple(values)


# Les postures assises/penchées ne réagissent pas toujours de façon monotone à
# la résolution YOLO : sur les faux vacants du 26/08, une silhouette valait 0,64
# à 640 mais 0,04 à 960. Les caméras portant une zone `presence` alternent donc
# ces échelles, une seule inférence par frame (aucun double passage GPU).
PRESENCE_YOLO_SCALES = _parse_imgsz_sequence(
    os.getenv('PRESENCE_YOLO_SCALES', '640,960')
)
# Une détection initiale + trois associations sont nécessaires pour confirmer un
# nouveau track OC-SORT en régime établi. Les échelles sont donc jouées par blocs.
PRESENCE_YOLO_SCALE_BLOCK_FRAMES = max(
    1, int(os.getenv('PRESENCE_YOLO_SCALE_BLOCK_FRAMES', '4'))
)

# Pour un poste, les pieds sont souvent masqués/coupés. Une boîte est membre de
# la zone si son point au sol est dedans OU si cette part de son corps recouvre
# le polygone. Sans effet sur les autres types de zones et sur les lignes.
PRESENCE_BBOX_OVERLAP_MIN = max(
    0.0, min(1.0, float(os.getenv('PRESENCE_BBOX_OVERLAP_MIN', '0.50')))
)
# Une détection encore en phase de confirmation peut manquer pendant le bloc
# d'échelle suivant. Pendant ce court délai, elle ne remet pas le chrono de
# vacance à zéro mais interdit de photographier la scène comme « poste vacant ».
PRESENCE_CANDIDATE_GRACE_SECONDS = max(
    0.0, float(os.getenv('PRESENCE_CANDIDATE_GRACE_SECONDS', '5.0'))
)
# Campagne d'observation : 0 désactive les échantillons. Une valeur positive
# enregistre périodiquement, pendant les seuls créneaux travaillés, une frame et
# l'état décisionnel de chaque zone de présence. Ce signal permet d'auditer aussi
# les périodes SANS alerte (faux négatifs / vrais négatifs).
PRESENCE_AUDIT_INTERVAL_SECONDS = max(
    0.0, float(os.getenv('PRESENCE_AUDIT_INTERVAL_SECONDS', '0'))
)

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
# Délai de CONFIRMATION (s) avant de compter une personne dans une zone : elle doit
# y rester SANS INTERRUPTION pendant ce délai. Sans lui, l'appartenance était
# instantanée — un simple passant gonflait l'occupation écrite en base et un flux
# continu de passants déclenchait de faux attroupements (CROWD_MIN_SECONDS ne
# regarde que le compte AGRÉGÉ, pas la durée de présence de CHAQUE personne).
# Défaut de repli quand la zone ne fixe pas son propre `min_presence_s` ;
# 0 = comptage immédiat (comportement d'avant).
ZONE_MIN_PRESENCE_SECONDS = float(os.getenv('ZONE_MIN_PRESENCE_SECONDS', '5.0'))
# Surveillance de PRÉSENCE AUX POSTES (zones `presence`) : durée pendant laquelle
# un poste doit rester inoccupé, DANS un créneau travaillé, avant d'être signalé.
# Valeur de REPLI uniquement — la vraie tolérance vient du régime horaire de la
# zone. 10 min : marge volontairement large, un agent assis derrière un comptoir
# est un cas de détection difficile et une fausse absence met en cause quelqu'un.
POST_ABSENCE_TOLERANCE_SECONDS = float(os.getenv('POST_ABSENCE_TOLERANCE_SECONDS', '600'))
# Fenêtre (s) de LISSAGE de l'occupation : la valeur publiée est la médiane des
# comptages de la fenêtre. Un raté de détection isolé n'écrit donc plus un point
# faux dans l'historique dont vivent toutes les stats. 0 = valeur instantanée.
OCCUPANCY_SMOOTH_SECONDS = float(os.getenv('OCCUPANCY_SMOOTH_SECONDS', '1.5'))
# Délai (s) avant de CONFIRMER une sortie de zone. Un track qui revient dans ce
# délai poursuit sa présence en cours : une occlusion ne coupe plus un temps
# d'attente en deux (ce qui le sous-estimait mécaniquement).
DWELL_EXIT_GRACE_SECONDS = float(os.getenv('DWELL_EXIT_GRACE_SECONDS', '2.0'))
# Survie (frames) de l'état par track (âge, côté engagé d'une ligne) après sa
# dernière apparition. Cet état était auparavant purgé dès UNE frame d'absence :
# le track revenait « côté inconnu » et son franchissement n'était jamais compté.
TRACK_STATE_TTL_FRAMES = int(os.getenv('TRACK_STATE_TTL_FRAMES', '90'))
# ── Robustesse du comptage de franchissement de ligne (anti-jitter / ID-switch) ──
# LINE_CROSS_MARGIN : bande morte perpendiculaire (unités image normalisées [0,1]).
#   Le côté « engagé » d'un track ne bascule qu'au-delà de cette marge de part et
#   d'autre → un track stationnant à cheval sur la ligne ne compte plus N fois.
LINE_CROSS_MARGIN = float(os.getenv('LINE_CROSS_MARGIN', '0.02'))
# Nombre de frames minimal entre deux comptages d'un même track sur une même ligne.
LINE_CROSS_COOLDOWN_FRAMES = int(os.getenv('LINE_CROSS_COOLDOWN_FRAMES', '15'))
# Âge de track minimal (frames observées) avant de compter un franchissement
# (évite les comptages parasites juste après une (ré)apparition / un ID-switch).
LINE_CROSS_MIN_AGE_FRAMES = int(os.getenv('LINE_CROSS_MIN_AGE_FRAMES', '3'))

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
# Délai avant l'arrêt du relais quand plus aucun lecteur n'est présent.
#
# 180s et non 30s : la passerelle HikCentral échoue à l'ÉTABLISSEMENT de session
# sous charge (mesuré : 100 % de réussite à 2 flux concurrents, ~83 % à 6 et 12).
# Ce qui la met en difficulté, c'est donc le nombre de sessions OUVERTES, pas leur
# durée. Or à 30 s le cycle était : le lecteur du Core décroche, le relais est tué,
# le lecteur revient, une nouvelle session est redemandée. Mesuré en production le
# 2026-09-04 : 190 arrêts « plus aucun lecteur » et 189 relances, dont 87 % en
# moins de 3 minutes (médiane 54 s) — autant d'établissements de session inutiles.
# Garder le relais tiède pendant 3 minutes absorbe ces décrochages brefs et
# transforme un flot de connexions en un jeu de sessions stables.
MEDIAMTX_ON_DEMAND_CLOSE_AFTER = os.getenv('MEDIAMTX_ON_DEMAND_CLOSE_AFTER', '180s')

# ----------------------
# Transcodage des sources HikCentral (HEVC/H.265 → H.264)
# ----------------------
# Les flux HikCentral (rtsp_s) sont en H.265, que le WebRTC navigateur NE décode
# pas → le relais les ré-encode en H.264. ⚠ Le relais ffmpeg tourne DANS LE
# CONTENEUR MEDIAMTX (image bluenviron/mediamtx:latest-ffmpeg), PAS dans le Core :
# l'encodeur doit exister dans CETTE image. L'image stock fournit libx264 /
# h264_qsv / h264_vaapi / h264_vulkan — mais PAS h264_nvenc (NVIDIA).
#   • libx264 (DÉFAUT) : CPU, présent partout, quasi gratuit sur un 360p@10fps.
#   • h264_vaapi / h264_qsv : accélération Intel/AMD si /dev/dri est monté.
#   • h264_nvenc : exigerait une image MediaMTX custom (ffmpeg nvenc + GPU monté).
# HIK_TRANSCODE_FLAGS : options ffmpeg (couplées à l'encodeur choisi).
HIK_TRANSCODE_ENCODER = os.getenv('HIK_TRANSCODE_ENCODER', 'libx264')
HIK_TRANSCODE_FLAGS = os.getenv(
    'HIK_TRANSCODE_FLAGS', '-preset veryfast -tune zerolatency -crf 26 -g 20'
)
# Démarrage SMS HikCentral lent à la 1re connexion → timeout on-demand allongé.
HIK_ONDEMAND_START_TIMEOUT = os.getenv('HIK_ONDEMAND_START_TIMEOUT', '30s')

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

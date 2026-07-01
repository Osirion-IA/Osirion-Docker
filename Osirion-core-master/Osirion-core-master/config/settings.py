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
# Résolution de TRAITEMENT (détection SCRFD + alignement/crop ArcFace). La vidéo
# AFFICHÉE (WebRTC servie par MediaMTX) est indépendante de cette valeur : la
# monter n'augmente QUE la qualité d'inférence et le coût GPU, jamais le débit
# vidéo navigateur. 640×480 (ancien défaut) réduisait les visages distants sous
# la taille exploitable par ArcFace (~50-60 px) → ils tombaient sous
# FACE_MIN_RECOG_SIZE et n'étaient jamais reconnus. 1280×720 les fait remonter.
# Dialer selon le budget GPU (RTX 4050 ↔ nombre de caméras) : 960×540 ou 640×480
# pour alléger. Ordre (largeur, hauteur) — attendu par cv2.resize.
FRAME_WIDTH = int(os.getenv('FRAME_WIDTH', '1280'))
FRAME_HEIGHT = int(os.getenv('FRAME_HEIGHT', '720'))
FRAME_SIZE = (FRAME_WIDTH, FRAME_HEIGHT)
PROCESS_EVERY_N_FRAME = 3         # GPU RTX 4050 : 1 frame sur 3 (~10 FPS effectifs vs 3 FPS CPU)
FRAME_QUEUE_MAXSIZE = 4           # Buffer légèrement plus grand pour absorber les pics GPU
FRAME_QUEUE_TIMEOUT = 0.1         # Timeout pour récupérer une frame de la queue (secondes)

# ----------------------
# Configuration du tracker — OC-SORT (Observation-Centric SORT)
# ----------------------
# OC-SORT remplace ByteTrack : moins de changements d'identité (ID switches) sur
# les mouvements rapides/erratiques. L'implémentation est AUTONOME
# (core/trackers/oc_sort.py, basée sur filterpy) et l'adaptateur OCSortTrackerAdapter
# préserve à l'identique l'API historique update(dets, img_info, img_size).
import types as _types

OC_SORT_ARGS = _types.SimpleNamespace(
    det_thresh=0.4,       # Seuil des détections haute confiance
    max_age=30,           # Frames avant suppression d'un track perdu (≈ track_buffer)
    iou_threshold=0.3,    # Seuil d'association IoU
    delta_t=3,            # Fenêtre de look-back pour l'estimation de vitesse
    inertia=0.2,          # Poids du terme d'inertie/momentum (OCM)
    use_byte=True,        # Conserver la récupération BYTE des détections faibles
)

# ----------------------
# Configuration de la reconnaissance faciale
# ----------------------
FACE_DETECTION_CONFIDENCE = 0.7   # Seuil de confiance pour la détection de visages

# Résolution d'entrée du détecteur SCRFD (buffalo_l). DOIT suivre FRAME_SIZE :
# si la frame est plus grande mais det_size reste petit, SCRFD réduit l'image en
# interne → on perd le bénéfice de la montée en résolution (visages distants à
# nouveau ratatinés). (960,960) = bon compromis précision/latence pour des frames
# 720p sur RTX 4050. Repasser à 640 pour alléger si la latence GPU monte trop.
_FACE_DET = int(os.getenv('FACE_DET_SIZE', '960'))
FACE_DET_SIZE = (_FACE_DET, _FACE_DET)

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
# Précision faciale — garde-fou de taille + vote temporel multi-frames
# ----------------------
# Garde-fou de taille de visage : on NE tente PAS de reconnaître un visage dont
# la boîte est plus petite que ce seuil (en px, sur le plus petit côté). Un visage
# minuscule donne un embedding ArcFace dégradé → décision peu fiable (faux
# positifs). Symétrique du gating crop du LPR (PLATE_MIN_CROP_*). 0 = désactivé.
#   Repère : les plaques de la caméra Hall font ~57 px ; un visage y est plus grand.
#   Si la reconnaissance se met à tout rejeter, abaisser cette valeur (ou 0).
# Relevé 40 → 70 px (qualité entreprise) : en dessous de ~70 px l'embedding ArcFace
# se dégrade nettement et alimente des faux positifs ; on préfère rester « Inconnu »
# et laisser le vote temporel rattraper le sujet quand il se rapproche.
FACE_MIN_RECOG_SIZE = int(os.getenv('FACE_MIN_RECOG_SIZE', '70'))

# Garde-fou de FRONTALITÉ : on NE tente PAS de reconnaître un visage de profil
# extrême. Score ∈ [0,1] estimé GRATUITEMENT à partir des 5 points SCRFD (symétrie
# horizontale nez↔yeux, cf. face_detection._frontality_from_kps) : 1.0 = frontal,
# → 0 = profil. ArcFace se dégrade fortement sur les profils → faux négatifs ET
# faux positifs. Repères : frontal ~0.7-1.0, ~30° yaw ~0.5, ~45° ~0.35, ~60° ~0.2.
# 0.25 (défaut) = ne rejette que les quasi-profils (> ~55°) ; le track reste
# « Inconnu » jusqu'à ce que la personne se tourne (le vote temporel le rattrape).
# 0 = désactivé. Indépendant de la résolution (c'est un ratio).
FACE_MIN_FRONTALITY = float(os.getenv('FACE_MIN_FRONTALITY', '0.25'))

# Garde-fou de NETTETÉ ciblé sur le CROP du visage (variance du Laplacien), distinct
# du BLUR_THRESHOLD qui porte sur la frame ENTIÈRE : un fond net avec un visage flou
# (sujet en mouvement) passe le gate frame mais donne un embedding ArcFace dégradé.
# DÉSACTIVÉ par défaut (0.0) car le seuil dépend de la taille du crop et de
# l'exposition : une valeur trop haute rejette des visages valides (et fausserait
# silencieusement les mesures EER du chapitre 4). Calibrer contre le harnais de
# mesure puis activer (~20-30 est un point de départ raisonnable en 720p).
# Activé par défaut à 25.0 (seuil CONSERVATEUR) : ne rejette que le flou de
# mouvement franc, qui produit un embedding ArcFace inexploitable. Abaisser/0 si
# des visages valides sont rejetés sur une caméra peu exposée.
FACE_CROP_MIN_SHARPNESS = float(os.getenv('FACE_CROP_MIN_SHARPNESS', '25.0'))

# ── Reconnaissance PONDÉRÉE par la QUALITÉ du visage (best-shot) ─────────────
# Les gardes-fous ci-dessus (taille/frontalité/netteté) JETTENT les pires visages
# (gates durs). Par-dessus, on pondère le vote temporel par un score de QUALITÉ
# ∈ [0,1] (frontalité × taille × netteté) : l'identité d'un track est alors
# décidée par ses BONNES frames, pas par n'importe quelle frame qui a passé les
# gates. Une frame floue / de profil léger / petite pèse moins dans le vote →
# moins de faux positifs (mauvais embedding qui matche par hasard) ET de faux
# négatifs (bon visage noyé sous des mauvais). Si toutes les qualités sont égales,
# le comportement est IDENTIQUE à l'ancien vote (aucune régression).
FACE_QUALITY_WEIGHTED_VOTE = os.getenv('FACE_QUALITY_WEIGHTED_VOTE', 'true').lower() == 'true'
# Tailles/nettetés de RÉFÉRENCE au-delà desquelles le facteur vaut 1.0 (qualité
# « idéale »). 110 px ≈ résolution native d'ArcFace (112). Netteté = variance du
# Laplacien sur le crop. En dessous, le facteur décroît linéairement vers 0.
FACE_QUALITY_REF_SIZE = int(os.getenv('FACE_QUALITY_REF_SIZE', '110'))
FACE_QUALITY_REF_SHARPNESS = float(os.getenv('FACE_QUALITY_REF_SHARPNESS', '120.0'))

# Vote temporel facial : au lieu de figer l'identité sur UNE seule frame (fragile
# quand le score cosinus frôle le seuil), on accumule les décisions FAISS le long
# d'un track et on ne CONFIRME une identité que si la MÊME personne est retrouvée
# au moins FACE_VOTE_MIN_AGREE fois avec un score moyen ≥ seuil adaptatif. Tant
# que ce n'est pas confirmé, le track reste « Inconnu » (pas de nom prématuré, pas
# d'alerte) et continue d'être ré-interrogé à chaque frame traitée. Au-delà de
# FACE_VOTE_MAX_ATTEMPTS tentatives sans consensus → figé « Inconnu ». Symétrique
# du vote temporel du LPR (PLATE_TEMPORAL_VOTING). false = ancien comportement
# mono-frame (zéro régression).
FACE_TEMPORAL_VOTING = os.getenv('FACE_TEMPORAL_VOTING', 'true').lower() == 'true'
FACE_VOTE_MIN_AGREE = int(os.getenv('FACE_VOTE_MIN_AGREE', '2'))
FACE_VOTE_MAX_ATTEMPTS = int(os.getenv('FACE_VOTE_MAX_ATTEMPTS', '5'))

# ── Fusion temporelle d'embeddings (best-of-stream) ──────────────────────────
# Au lieu d'interroger FAISS avec l'embedding d'UNE frame, on envoie la MOYENNE
# re-normalisée L2 des derniers embeddings du track. Le bruit par frame s'annule →
# requête plus stable, score cosinus plus haut et plus régulier. window ≤ 1 ⇒
# comportement mono-frame d'origine (aucune régression).
FACE_EMBEDDING_FUSION = os.getenv('FACE_EMBEDDING_FUSION', 'true').lower() == 'true'
FACE_EMBED_FUSION_WINDOW = int(os.getenv('FACE_EMBED_FUSION_WINDOW', '5'))

# ── Normalisation d'éclairage CLAHE (canal L, LAB) avant ArcFace ─────────────
# Égalise localement le contraste du crop avant extraction → récupère les visages
# en contre-jour / ombres dures. FACE_CLAHE_CLIP = limite d'écrêtage CLAHE.
FACE_CLAHE_ENABLED = os.getenv('FACE_CLAHE_ENABLED', 'true').lower() == 'true'
FACE_CLAHE_CLIP = float(os.getenv('FACE_CLAHE_CLIP', '2.0'))

# ── Durcissement du cache global (anti faux-positif « collant ») ─────────────
# Un hit du cache global ne court-circuite le vote temporel que si son score est
# ≥ ce seuil. En dessous, le consensus multi-frames prime → un unique match
# mono-frame de confiance moyenne ne peut plus figer une mauvaise identité pour
# toute la durée du cache (GLOBAL_CACHE_TTL_SECONDS).
CACHE_TRUST_THRESHOLD = float(os.getenv('CACHE_TRUST_THRESHOLD', '0.88'))

# ----------------------
# Sprint 2 — Backbone & accélération d'inférence
# ----------------------
# Pack de modèles InsightFace. 'antelopev2' = SCRFD-10G (détection) + glintr100
# (ResNet-100, reconnaissance) → précision « entreprise », nettement au-dessus de
# 'buffalo_l' (ResNet-50). Les deux produisent du 512-D MAIS dans des espaces
# d'embedding DIFFÉRENTS et INCOMPATIBLES : changer de pack invalide TOUTE la
# galerie existante → ré-enrôlement obligatoire. Le backend (enrôlement) DOIT
# utiliser le MÊME pack (cf. app/services/embeddings_service.py qui lit la même
# variable INSIGHTFACE_MODEL_PACK), sinon requête (Core) et galerie (backend) ne
# sont pas comparables.
INSIGHTFACE_MODEL_PACK = os.getenv('INSIGHTFACE_MODEL_PACK', 'antelopev2')

# ── ONNX Runtime : SessionOptions (anti-monopolisation CPU) ──────────────────
# Borne les pools de threads ORT pour ne pas saturer tous les cœurs (plusieurs
# caméras + LPR + serveur web partagent la machine). Sur GPU, l'essentiel du
# calcul est sur le device ; ces threads ne servent qu'au pré/post-traitement CPU.
ONNX_INTRA_OP_THREADS = int(os.getenv('ONNX_INTRA_OP_THREADS', '4'))
ONNX_INTER_OP_THREADS = int(os.getenv('ONNX_INTER_OP_THREADS', '2'))

# ── ONNX Runtime : provider_options CUDA ─────────────────────────────────────
# gpu_mem_limit = PLAFOND de l'arène mémoire (pas une réservation) → empêche une
# session de monopoliser la VRAM (essentiel si plusieurs sessions cohabitent).
ONNX_GPU_MEM_LIMIT_GB = float(os.getenv('ONNX_GPU_MEM_LIMIT_GB', '2'))
ONNX_ARENA_EXTEND_STRATEGY = os.getenv('ONNX_ARENA_EXTEND_STRATEGY', 'kNextPowerOfTwo')
# EXHAUSTIVE = recherche du meilleur noyau de convolution au 1er passage (coût de
# démarrage, gain en régime permanent). 'HEURISTIC' pour un démarrage plus rapide.
ONNX_CUDNN_CONV_ALGO = os.getenv('ONNX_CUDNN_CONV_ALGO', 'EXHAUSTIVE')

# ── FP16 via TensorRT (optionnel) ────────────────────────────────────────────
# Le CUDAExecutionProvider n'a PAS d'option FP16 (il exécute le graphe ONNX dans
# sa précision native, FP32). Le vrai levier FP16 sans reconvertir le modèle est
# le TensorrtExecutionProvider (trt_fp16_enable). Désactivé par défaut : le 1er
# build de moteur TRT est long et dépend du paquet ORT. Activer en connaissance
# de cause (un cache moteur est écrit dans ONNX_TRT_CACHE_DIR).
FACE_TRT_FP16 = os.getenv('FACE_TRT_FP16', 'false').lower() == 'true'
ONNX_TRT_CACHE_DIR = os.getenv('ONNX_TRT_CACHE_DIR', '/tmp/trt_cache')

# ── Worker d'inférence dédié (producteur-consommateur) ───────────────────────
# true (défaut) : toutes les caméras SOUMETTENT leurs frames à un (ou des) thread(s)
# d'inférence dédié(s) et attendent le résultat → l'accès au GPU est sérialisé sur
# un propriétaire unique (contexte CUDA stable, mémoire déterministe) au lieu que N
# threads caméra tapent la même session ORT. false : appel direct (session partagée,
# comportement Sprint 1).
FACE_INFERENCE_WORKER = os.getenv('FACE_INFERENCE_WORKER', 'true').lower() == 'true'
# Taille du pool de workers. 1 (défaut) = UNE session partagée (~1 GB VRAM). > 1 =
# une session PROPRE par worker (≈ +1 GB chacune) → débit accru au prix de la VRAM.
FACE_INFERENCE_WORKERS = max(1, int(os.getenv('FACE_INFERENCE_WORKERS', '1')))
# Garde-fou : délai max d'attente d'un résultat d'inférence (s) avant d'abandonner
# la frame (retourne 0 visage) plutôt que de bloquer le thread caméra indéfiniment.
FACE_INFER_TIMEOUT = float(os.getenv('FACE_INFER_TIMEOUT', '10'))

# ----------------------
# Recherche d'embeddings LOCALE (réplique FAISS dans le Core) — OPT-IN
# ----------------------
# false (défaut) : la reconnaissance interroge le backend en HTTP (comportement
#   historique, inchangé).
# true : le Core garde une copie RAM de la galerie (chargée au démarrage +
#   réconciliée périodiquement) et fait la recherche FAISS EN LOCAL (~0.1 ms vs
#   ~5-15 ms en HTTP). PostgreSQL reste géré uniquement par le backend.
#   Tout échec/indisponibilité de l'index local → repli HTTP automatique.
FAISS_LOCAL = os.getenv('FAISS_LOCAL', 'false').lower() == 'true'
# Intervalle (s) du poll de version galerie : borne le délai de prise en compte
# d'un nouvel enrôlement / changement de blacklist côté Core.
FAISS_LOCAL_RECONCILE_SECONDS = int(os.getenv('FAISS_LOCAL_RECONCILE_SECONDS', '15'))

# ----------------------
# Configuration de la reconnexion RTSP
# ----------------------
RECONNECTION_SLEEP = 0.1          # Délai avant tentative de reconnexion RTSP (secondes)
MAX_RECONNECTION_ATTEMPTS = 5     # Tentatives avant d'escalader le log en ERROR (la reconnexion ne s'arrête JAMAIS : on continue ensuite au délai plafond — reprise auto après longue coupure)
RECONNECTION_BASE_DELAY = 1.0     # Délai de base pour le backoff exponentiel (secondes)
MAX_RECONNECTION_DELAY = 30.0     # Délai maximum entre les tentatives de reconnexion (secondes)
FRAME_FAILURE_THRESHOLD = 10      # Nombre d'échecs consécutifs avant de déclencher une reconnexion

# ----------------------
# Supervision des caméras à chaud (hot-add / hot-remove)
# ----------------------
# Intervalle (s) du thread de supervision : le Core ré-interroge périodiquement
# la liste des caméras du backend et applique les changements À CHAUD, sans
# redémarrage — ajout d'une nouvelle caméra active, (dé)activation, suppression,
# et redémarrage d'un thread caméra mort. 0 = supervision désactivée (ancien
# comportement : snapshot unique au démarrage).
CAMERA_REFRESH_SECONDS = int(os.getenv('CAMERA_REFRESH_SECONDS', '15'))

# ----------------------
# Dispositif de MESURE (évaluation du chapitre 4 du mémoire)
# ----------------------
# Le Core journalise des métriques exploitables hors-ligne (latence, débit, cache,
# GPU, décisions de reconnaissance + vérité terrain, lectures de plaques) dans un
# fichier JSON Lines (MEASURE_FILE), dépouillé par tools/analyze_metrics.py.
# Activation/fichier sont lus directement par utils.measurement (MEASURE_ENABLED,
# MEASURE_FILE). Ici : seul l'intervalle d'échantillonnage système (s).
MEASURE_SAMPLE_SECONDS = int(os.getenv('MEASURE_SAMPLE_SECONDS', '5'))

# ----------------------
# Source de capture vidéo (architecture VMS — Phase 2)
# ----------------------
# READ_FROM_MEDIAMTX=true : le Core lit le flux RTSP REPUBLIÉ par MediaMTX
# (rtsp://<base>/cam<id>) au lieu de taper la caméra directement. Résultat : UNE
# SEULE connexion à la caméra physique (faite par MediaMTX), partagée entre l'IA
# (Core) et la vidéo navigateur (WebRTC). Réduit la charge caméra/réseau et la
# perte de paquets. false = ancien comportement (Core ouvre cam["rtsp_url"]).
READ_FROM_MEDIAMTX = os.getenv('READ_FROM_MEDIAMTX', 'false').lower() == 'true'
MEDIAMTX_RTSP_BASE = os.getenv('MEDIAMTX_RTSP_BASE', 'mediamtx:8554')  # hôte:port RTSP interne

# ----------------------
# Chemins MediaMTX dynamiques (1 par caméra) — voir services.mediamtx_path_service
# ----------------------
# Plutôt que de déclarer chaque caméra dans mediamtx.yml + .env
# (MTX_PATHS_CAM<id>_SOURCE), le Core crée/met à jour/supprime à chaud le chemin
# `cam<id>` via l'API HTTP de MediaMTX, à partir du rtsp_url renvoyé par le
# backend. Une caméra ajoutée à chaud obtient ainsi automatiquement sa source.
# L'API n'est PAS publiée vers l'hôte (réseau Docker interne uniquement).
MANAGE_MEDIAMTX_PATHS = os.getenv('MANAGE_MEDIAMTX_PATHS', 'true').lower() == 'true'
MEDIAMTX_API_BASE = os.getenv('MEDIAMTX_API_BASE', 'http://mediamtx:9997')
# Transport RTSP imposé au pull caméra côté MediaMTX (tcp = pas de perte RTP).
MEDIAMTX_RTSP_TRANSPORT = os.getenv('MEDIAMTX_RTSP_TRANSPORT', 'tcp')
# Fermeture du flux caméra après X sans lecteur (sourceOnDemand).
MEDIAMTX_ON_DEMAND_CLOSE_AFTER = os.getenv('MEDIAMTX_ON_DEMAND_CLOSE_AFTER', '30s')

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
# Seuil du cache global d'identité (cosine brut ∈ [0,1]). IMPORTANT : un hit cache
# (core/tracking_processor._decide_cached) CONFIRME une identité immédiatement et
# COURT-CIRCUITE le vote temporel multi-frames. Il doit donc être PLUS STRICT que
# le seuil de première reconnaissance (RECOGNITION_THRESHOLD=0.45 / floor 0.35) :
# seules des identités à HAUTE confiance peuplent et servent le cache, sinon une
# erreur cache « colle » pendant tout le TTL (GLOBAL_CACHE_TTL_SECONDS) et se
# propage entre caméras sans repasser par le vote. 0.55 (défaut) = nettement
# au-dessus de la bande de reconnaissance, tout en captant les vraies ré-ID
# (cosine live même personne ≈ 0.45-0.80). Monter vers 0.60 pour un cache encore
# plus prudent (au prix de plus de recherches FAISS). Était 0.50 ; 0.75 dans
# l'ancien .env relevait de l'échelle (cosine+1)/2, désormais caduque.
GLOBAL_SIMILARITY_THRESHOLD = float(os.getenv('GLOBAL_SIMILARITY_THRESHOLD', '0.55'))  # cosine brut ∈ [0,1]
# -----------------------------------------
# configuration des événements (ex: reconnaissance, entrée/sortie)
# -----------------------------------------

EVENTS = ["RECOGNITION","ENTRY","EXIT","DETECTION","PLATE_RECOGNITION","UNKNOWN_FACE"]  # Types d'événements à créer

# -----------------------------------------
# Événement « visage non reconnu » (UNKNOWN_FACE)
# -----------------------------------------
# Activation OPT-IN : désactivé par défaut → ne change RIEN au comportement
# existant. Quand activé (flag ci-dessous ou toggle frontend /api/unknown-face/
# toggle), un visage DÉTECTÉ mais NON reconnu (aucun match au-dessus du seuil et
# absent du cache global) génère un événement DISTINCT (event_type=UNKNOWN_FACE,
# person_id=NULL). Le throttling naturel de la ré-identification (REIDENTIFICATION_
# INTERVAL) borne la fréquence : au plus un événement par track et par intervalle.
ENABLE_UNKNOWN_FACE_EVENT = os.getenv('ENABLE_UNKNOWN_FACE_EVENT', 'false').lower() == 'true'

# -----------------------------------------
# Reconnaissance faciale (pipeline principal) — activable/désactivable à chaud
# -----------------------------------------
# ⚠️ DÉFAUT = true : le facial est le pipeline PRINCIPAL. Le toggle (frontend
# /api/face/toggle) permet de le suspendre à chaud (ex. caméra dédiée plaques)
# SANS arrêter le Core : quand il est coupé, SCRFD/ArcFace et la reconnaissance
# sont sautés, mais le LPR et la publication des métadonnées continuent.
ENABLE_FACE_RECOGNITION = os.getenv('ENABLE_FACE_RECOGNITION', 'true').lower() == 'true'

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

# Longueur plausible d'une plaque (filtre les faux positifs OCR). Sert aussi à
# construire le validateur universel ^[A-Z0-9]{MIN,MAX}$ (layout-agnostique).
PLATE_MIN_CHARS = int(os.getenv('PLATE_MIN_CHARS', '4'))
PLATE_MAX_CHARS = int(os.getenv('PLATE_MAX_CHARS', '10'))

# Ordre de lecture spatial 2D — filtrage géométrique du bruit (Step 1) : un bloc
# OCR dont la hauteur < ce ratio × hauteur max est ignoré (petit texte non
# essentiel : nom de pays, label structurel). 0.45 = 45 %.
PLATE_MIN_TEXT_HEIGHT_RATIO = float(os.getenv('PLATE_MIN_TEXT_HEIGHT_RATIO', '0.45'))

# Seuil de similarité pour la recherche floue côté backend (/plates/search)
PLATE_SEARCH_THRESHOLD = float(os.getenv('PLATE_SEARCH_THRESHOLD', '0.82'))

# Durée de vie (en frames) d'une plaque en cache de track avant nettoyage
PLATE_CACHE_TTL_FRAMES = int(os.getenv('PLATE_CACHE_TTL_FRAMES', '600'))

# Couleurs d'annotation des plaques (BGR) — distinctes des visages (vert/rouge)
COLOR_PLATE = (0, 200, 255)            # Jaune/orangé : plaque détectée/lue
COLOR_PLATE_BLACKLIST = (0, 0, 255)    # Rouge : plaque blacklistée (alerte)
COLOR_PLATE_KNOWN = (255, 200, 0)      # Bleu clair : plaque connue (non blacklistée)

# -----------------------------------------
# Module LPR — OPTIMISATIONS latence & précision
# -----------------------------------------
# Tous ces réglages ont des valeurs par défaut SÛRES : le module se comporte au
# moins aussi bien qu'avant, et chaque nouveau chemin retombe gracieusement sur
# l'ancien comportement en cas de problème (jamais d'impact sur le facial).

# ── Latence : cadence de DÉTECTION plaque ───────────────────────────────────
# La détection YOLO de plaque ne tourne qu'1 frame TRAITÉE sur N (le cache OCR
# par track couvre les frames intermédiaires via annotate_cached). 1 = ancien
# comportement (détecter à chaque frame traitée). 2-3 = ~2-3× moins de YOLO.
PLATE_PROCESS_EVERY_N = int(os.getenv('PLATE_PROCESS_EVERY_N', '2'))

# ── Latence : OCR découplé du thread caméra ─────────────────────────────────
# EasyOCR + l'ordre de lecture spatial 2D tournent dans un thread worker OCR
# dédié (file FIFO) ; le thread caméra ne fait que détecter/tracker/soumettre →
# aucune saccade sur la boucle de tracking WebRTC. Borné par le gating 1 crop/track.
PLATE_OCR_QUEUE_MAXSIZE = int(os.getenv('PLATE_OCR_QUEUE_MAXSIZE', '32'))

# ── Latence : résolution réseau découplée du thread caméra ──────────────────
# La recherche floue + l'envoi d'événement partent dans un thread worker dédié
# (file FIFO) ; le thread caméra n'est JAMAIS bloqué par le réseau.
PLATE_LOOKUP_QUEUE_MAXSIZE = int(os.getenv('PLATE_LOOKUP_QUEUE_MAXSIZE', '64'))

# ── Latence/précision : gating du crop avant OCR ────────────────────────────
# On n'OCR pas les plaques trop petites (illisibles, gaspillage GPU/CPU).
PLATE_MIN_CROP_WIDTH = int(os.getenv('PLATE_MIN_CROP_WIDTH', '60'))
PLATE_MIN_CROP_HEIGHT = int(os.getenv('PLATE_MIN_CROP_HEIGHT', '18'))
# Filtre de netteté du crop (variance du Laplacien). 0.0 = désactivé (défaut sûr,
# évite de tout filtrer en faible luminosité). Mettre ~15-30 pour rejeter le flou.
PLATE_CROP_MIN_SHARPNESS = float(os.getenv('PLATE_CROP_MIN_SHARPNESS', '0.0'))

# ── Précision : vote temporel multi-frames (agrégation OCR le long d'un track)
# Au lieu de figer la 1re lecture haute-confiance, on accumule les lectures et
# on vote caractère par caractère. Une plaque est "définitive" quand le même
# consensus est observé PLATE_VOTE_MIN_AGREE fois (et conf moyenne ≥ ocr_good),
# ou que PLATE_OCR_MAX_ATTEMPTS est atteint.
PLATE_TEMPORAL_VOTING = os.getenv('PLATE_TEMPORAL_VOTING', 'true').lower() == 'true'
PLATE_VOTE_MIN_AGREE = int(os.getenv('PLATE_VOTE_MIN_AGREE', '2'))

# ── Précision : pré-traitement du crop avant OCR ────────────────────────────
# Upscale des petits crops + niveaux de gris + CLAHE (contraste adaptatif).
# Sûr et peu coûteux. Le deskew (correction de perspective) est plus agressif,
# donc désactivé par défaut.
PLATE_PREPROCESS = os.getenv('PLATE_PREPROCESS', 'true').lower() == 'true'
PLATE_PREPROCESS_TARGET_HEIGHT = int(os.getenv('PLATE_PREPROCESS_TARGET_HEIGHT', '64'))
PLATE_DESKEW = os.getenv('PLATE_DESKEW', 'false').lower() == 'true'

# Robustesse à la FORTE LUMINOSITÉ (surexposition, reflets, gradients) :
# suppression du glare (inpainting des pixels saturés) + normalisation
# d'illumination (division par fond flou) + gamma adaptatif. Tout est
# CONDITIONNEL (ne se déclenche que sur les crops réellement trop clairs),
# donc activé par défaut sans risque sur les conditions normales/faible lumière.
PLATE_ILLUMINATION_ROBUST = os.getenv('PLATE_ILLUMINATION_ROBUST', 'true').lower() == 'true'

# ── Latence : demi-précision (FP16) du YOLO de plaque sur GPU ───────────────
# Accélère l'inférence sur GPU. Repli automatique en FP32 si une inférence FP16
# échoue (le flag se désactive tout seul → jamais de crash).
PLATE_YOLO_HALF = os.getenv('PLATE_YOLO_HALF', 'true').lower() == 'true'

# ── Précision : validation par format (regex) — OPTIONNEL ───────────────────
# Vide = désactivé (défaut). Ex. pour ne garder que 6-8 alphanumériques :
#   PLATE_FORMAT_REGEX='^[A-Z0-9]{6,8}$'
# Une lecture qui ne matche pas n'est jamais "finalisée" (réduit les faux positifs).
PLATE_FORMAT_REGEX = os.getenv('PLATE_FORMAT_REGEX', '').strip()
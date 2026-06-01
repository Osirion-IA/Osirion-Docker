# plate_detection.py
"""
Détection + OCR des plaques d'immatriculation (singletons chargés une fois).

Architecture symétrique de face_detection.py :
  - face_detection : SCRFD (détection) + ArcFace (embedding)   → visages
  - plate_detection: YOLO  (détection) + EasyOCR (lecture texte)→ plaques

Dégradation gracieuse (CRITIQUE) :
  Si ultralytics / easyocr sont absents, ou si les poids YOLO sont introuvables,
  le module se charge quand même mais expose LPR_AVAILABLE = False et
  detect_plates() renvoie []. Le pipeline facial existant n'est JAMAIS impacté.

Les modèles (YOLO + EasyOCR) sont des singletons partagés entre toutes les
caméras/threads ; les appels d'inférence sont protégés par des verrous pour
éviter les problèmes de concurrence CUDA / torch.
"""
import os
import re
import threading
from typing import List, Tuple, Optional

import numpy as np

from utils.logger import get_logger

logger = get_logger(__name__)

# ── Détection de la disponibilité GPU (via torch, tiré par ultralytics) ──────
try:
    import torch  # noqa: F401
    _USE_GPU = bool(torch.cuda.is_available())
except Exception:
    _USE_GPU = False

_NON_ALNUM = re.compile(r"[^A-Z0-9]")

LPR_AVAILABLE = False        # passe à True si tous les modèles sont chargés
_PLATE_MODEL = None          # ultralytics.YOLO
_OCR_READER = None           # easyocr.Reader
_yolo_lock = threading.Lock()
_ocr_lock = threading.Lock()

# Config OCR appliquée au chargement (lue depuis config.settings si dispo)
try:
    from config import settings as _cfg
    _MODEL_PATH = getattr(_cfg, 'PLATE_MODEL_PATH', 'license_plate_detector.pt')
    _OCR_LANGS = getattr(_cfg, 'PLATE_OCR_LANGS', ['en'])
    _OCR_ALLOWLIST = getattr(_cfg, 'PLATE_OCR_ALLOWLIST', 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789')
    _MIN_CHARS = getattr(_cfg, 'PLATE_MIN_CHARS', 4)
    _MAX_CHARS = getattr(_cfg, 'PLATE_MAX_CHARS', 10)
except Exception:
    _MODEL_PATH = os.getenv('PLATE_MODEL_PATH', 'license_plate_detector.pt')
    _OCR_LANGS = ['en']
    _OCR_ALLOWLIST = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
    _MIN_CHARS, _MAX_CHARS = 4, 10


def normalize_plate(raw: Optional[str]) -> str:
    """Majuscules + suppression de tout caractère non alphanumérique.
    Identique à la normalisation backend (app/utils/plate_utils.normalize_plate)."""
    if not raw:
        return ""
    return _NON_ALNUM.sub("", raw.upper())


def _load_models() -> None:
    """Charge YOLO + EasyOCR une seule fois. N'échoue jamais 'fort'."""
    global LPR_AVAILABLE, _PLATE_MODEL, _OCR_READER

    # 1) Détecteur de plaque (Ultralytics YOLO)
    try:
        from ultralytics import YOLO
    except Exception as e:
        logger.warning(f"[LPR] ultralytics indisponible — module plaques désactivé ({e})")
        return

    if not os.path.exists(_MODEL_PATH):
        logger.warning(
            f"[LPR] Poids YOLO de plaque introuvables : '{_MODEL_PATH}'. "
            "Module plaques désactivé. Placez un modèle (ex. license_plate_detector.pt) "
            "ou définissez PLATE_MODEL_PATH. Le pipeline facial reste inchangé."
        )
        return

    try:
        _PLATE_MODEL = YOLO(_MODEL_PATH)
        logger.info(f"[LPR] Modèle YOLO de plaque chargé : {_MODEL_PATH} (GPU={_USE_GPU})")
    except Exception as e:
        logger.error(f"[LPR] Échec chargement YOLO de plaque : {e}")
        return

    # 2) OCR (EasyOCR)
    try:
        import easyocr
        _OCR_READER = easyocr.Reader(_OCR_LANGS, gpu=_USE_GPU)
        logger.info(f"[LPR] EasyOCR chargé (langs={_OCR_LANGS}, GPU={_USE_GPU})")
    except Exception as e:
        logger.error(f"[LPR] Échec chargement EasyOCR — module plaques désactivé ({e})")
        _PLATE_MODEL = None
        return

    LPR_AVAILABLE = True
    logger.info("[LPR] Module de reconnaissance de plaques OPÉRATIONNEL.")


# Chargement au démarrage (non bloquant en cas d'échec)
_load_models()


def detect_plates(frame: np.ndarray, confidence_threshold: float = 0.45) -> List[Tuple]:
    """
    Détecte les plaques dans la frame.

    Returns:
        Liste de ((x, y, w, h), det_conf). Vide si LPR indisponible ou aucune plaque.
    """
    if not LPR_AVAILABLE or _PLATE_MODEL is None or frame is None or frame.size == 0:
        return []

    h, w = frame.shape[:2]
    out: List[Tuple] = []
    try:
        with _yolo_lock:
            results = _PLATE_MODEL(frame, verbose=False)[0]
    except Exception as e:
        logger.error(f"[LPR] Erreur détection YOLO : {e}")
        return []

    if results.boxes is None:
        return []

    for box in results.boxes:
        conf = float(box.conf[0])
        if conf < confidence_threshold:
            continue
        x1, y1, x2, y2 = box.xyxy[0].int().tolist()
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)
        if x2 <= x1 or y2 <= y1:
            continue
        out.append(((x1, y1, x2 - x1, y2 - y1), conf))
    return out


def read_plate_text(plate_crop: np.ndarray) -> Tuple[str, float]:
    """
    Lit le texte d'un crop de plaque via EasyOCR.

    Returns:
        (texte_normalisé, confiance_ocr). ("", 0.0) si échec / illisible.
    """
    if not LPR_AVAILABLE or _OCR_READER is None or plate_crop is None or plate_crop.size == 0:
        return "", 0.0

    try:
        with _ocr_lock:
            # detail=1 → [(bbox, text, conf), ...]
            detections = _OCR_READER.readtext(
                plate_crop, allowlist=_OCR_ALLOWLIST, detail=1, paragraph=False
            )
    except Exception as e:
        logger.error(f"[LPR] Erreur OCR : {e}")
        return "", 0.0

    if not detections:
        return "", 0.0

    # Concatène les fragments lus (gauche→droite) et moyenne pondérée des confiances.
    detections.sort(key=lambda d: d[0][0][0])  # tri par x du coin haut-gauche
    text_parts, confs = [], []
    for _bbox, txt, conf in detections:
        norm = normalize_plate(txt)
        if norm:
            text_parts.append(norm)
            confs.append(float(conf))

    plate = "".join(text_parts)
    if not (_MIN_CHARS <= len(plate) <= _MAX_CHARS):
        return "", 0.0

    avg_conf = float(np.mean(confs)) if confs else 0.0
    return plate, avg_conf

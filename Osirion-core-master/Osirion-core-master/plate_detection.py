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
from typing import Dict, List, Tuple, Optional

import cv2
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

# Demi-précision (FP16) sur GPU — peut se désactiver tout seul en cas d'échec.
_yolo_half = False

# Config OCR appliquée au chargement (lue depuis config.settings si dispo)
try:
    from config import settings as _cfg
    _MODEL_PATH = getattr(_cfg, 'PLATE_MODEL_PATH', 'license_plate_detector.pt')
    _OCR_LANGS = getattr(_cfg, 'PLATE_OCR_LANGS', ['en'])
    _OCR_ALLOWLIST = getattr(_cfg, 'PLATE_OCR_ALLOWLIST', 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789')
    _MIN_CHARS = getattr(_cfg, 'PLATE_MIN_CHARS', 4)
    _MAX_CHARS = getattr(_cfg, 'PLATE_MAX_CHARS', 10)
    _PREPROCESS = getattr(_cfg, 'PLATE_PREPROCESS', True)
    _PREPROCESS_TARGET_H = getattr(_cfg, 'PLATE_PREPROCESS_TARGET_HEIGHT', 64)
    _DESKEW = getattr(_cfg, 'PLATE_DESKEW', False)
    _ILLUMINATION_ROBUST = getattr(_cfg, 'PLATE_ILLUMINATION_ROBUST', True)
    _yolo_half = bool(getattr(_cfg, 'PLATE_YOLO_HALF', True))
except Exception:
    _MODEL_PATH = os.getenv('PLATE_MODEL_PATH', 'license_plate_detector.pt')
    _OCR_LANGS = ['en']
    _OCR_ALLOWLIST = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
    _MIN_CHARS, _MAX_CHARS = 4, 10
    _PREPROCESS, _PREPROCESS_TARGET_H, _DESKEW = True, 64, False
    _ILLUMINATION_ROBUST = True
    _yolo_half = True

# La demi-précision n'a de sens que sur GPU.
_yolo_half = _yolo_half and _USE_GPU

# Validateur alphanumérique universel (layout-agnostique, sans format pays).
# Accepte UNIQUEMENT lettres majuscules + chiffres, longueur [_MIN_CHARS.._MAX_CHARS].
# Avec les défauts (4..10) cela donne exactement ^[A-Z0-9]{4,10}$.
_PLATE_VALIDATOR = re.compile(rf"^[A-Z0-9]{{{_MIN_CHARS},{_MAX_CHARS}}}$")

# En dessous de ce ratio par rapport à la plus grande hauteur de texte, un bloc
# OCR est considéré comme du « petit texte » non essentiel (nom de pays, label
# structurel…) et ignoré. Réglable via config (défaut 0.45 = 45 %).
try:
    _MIN_TEXT_HEIGHT_RATIO = float(getattr(_cfg, 'PLATE_MIN_TEXT_HEIGHT_RATIO', 0.45))
except Exception:
    _MIN_TEXT_HEIGHT_RATIO = 0.45


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
    logger.info(f"[LPR] Module de reconnaissance de plaques OPÉRATIONNEL (FP16={_yolo_half}).")

    # Warm-up : 1re inférence "à blanc" pour éviter le pic de latence sur la
    # première vraie plaque (allocation CUDA, compilation des kernels…).
    try:
        dummy = np.zeros((480, 640, 3), dtype=np.uint8)
        detect_plates(dummy, confidence_threshold=0.99)   # ne détectera rien
        read_plate_text(np.zeros((40, 120, 3), dtype=np.uint8))
        logger.info("[LPR] Warm-up des modèles terminé.")
    except Exception as e:
        logger.debug(f"[LPR] Warm-up ignoré ({e})")


def _preprocess_crop(crop: np.ndarray) -> np.ndarray:
    """
    Pré-traitement du crop de plaque pour fiabiliser l'OCR :
      1) upscale des petits crops vers une hauteur cible (l'OCR lit mieux),
      2) robustesse à l'éclairage (opt., conditionnel) : suppression du glare →
         gamma adaptatif → normalisation d'illumination (si crop clair/reflets),
      3) niveaux de gris + CLAHE (contraste adaptatif),
      4) deskew optionnel (correction de perspective via minAreaRect).

    Best-effort : en cas d'erreur, on renvoie le crop d'origine (jamais de crash).
    """
    if not _PREPROCESS or crop is None or crop.size == 0:
        return crop
    try:
        out = crop
        h, w = out.shape[:2]
        # 1) Upscale si la plaque est petite (interp. cubique pour le texte).
        if 0 < h < _PREPROCESS_TARGET_H:
            scale = _PREPROCESS_TARGET_H / float(h)
            out = cv2.resize(out, (max(1, int(w * scale)), _PREPROCESS_TARGET_H),
                             interpolation=cv2.INTER_CUBIC)

        # 2) Gris.
        gray = cv2.cvtColor(out, cv2.COLOR_BGR2GRAY) if out.ndim == 3 else out

        # Robustesse forte luminosité — bloc ENTIÈREMENT conditionnel : ne se
        # déclenche que si le crop est réellement clair ou présente des reflets.
        # Un crop normal/sombre est laissé intact → zéro régression.
        if _ILLUMINATION_ROBUST:
            mean_lum = float(gray.mean())
            sat_ratio = float((gray >= 245).mean())   # part de pixels quasi-saturés
            if mean_lum > 170.0 or sat_ratio > 0.02:
                gray = _suppress_glare(gray)          # reflets spéculaires
                gray = _adaptive_gamma(gray)          # surexposition (gamma > 1)
                gray = _normalize_illumination(gray)  # gradients d'éclairage

        # 3) CLAHE (contraste local adaptatif).
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        gray = clahe.apply(gray)

        # 4) Deskew optionnel.
        if _DESKEW:
            gray = _deskew(gray)

        # EasyOCR accepte le niveaux de gris ; on repasse en 3 canaux pour rester
        # compatible avec toutes les versions.
        return cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    except Exception as e:
        logger.debug(f"[LPR] pré-traitement crop ignoré ({e})")
        return crop


def _suppress_glare(gray: np.ndarray, sat_thresh: int = 245) -> np.ndarray:
    """Masque les reflets quasi-saturés (taches blanches) et les reconstruit par
    inpainting. N'agit que s'il y a réellement du glare (sinon retour inchangé)."""
    try:
        mask = (gray >= sat_thresh).astype(np.uint8) * 255
        if float(mask.mean()) > 1.0:   # > ~0.4% de pixels saturés
            mask = cv2.dilate(mask, np.ones((3, 3), np.uint8), iterations=1)
            gray = cv2.inpaint(gray, mask, 3, cv2.INPAINT_TELEA)
    except Exception:
        pass
    return gray


def _normalize_illumination(gray: np.ndarray) -> np.ndarray:
    """Division par un fond flou → aplatit les gradients d'éclairage et atténue
    le « washout » (mi-soleil/mi-ombre, surexposition partielle)."""
    try:
        sigma = max(gray.shape) / 8.0
        blur = cv2.GaussianBlur(gray, (0, 0), sigmaX=sigma)
        return cv2.divide(gray, blur, scale=255)
    except Exception:
        return gray


def _adaptive_gamma(gray: np.ndarray) -> np.ndarray:
    """Assombrit (gamma > 1) uniquement les crops surexposés. En dessous de
    luminance moyenne 180, retour inchangé → zéro impact en conditions normales."""
    try:
        m = float(gray.mean())
        if m <= 180.0:
            return gray
        gamma = 1.0 + (m - 180.0) / 75.0
        lut = (((np.arange(256) / 255.0) ** gamma) * 255).astype(np.uint8)
        return cv2.LUT(gray, lut)
    except Exception:
        return gray


def _deskew(gray: np.ndarray) -> np.ndarray:
    """Redresse une plaque inclinée via l'angle du rectangle englobant minimal."""
    try:
        _, th = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        coords = np.column_stack(np.where(th > 0))
        if coords.shape[0] < 20:
            return gray
        angle = cv2.minAreaRect(coords)[-1]
        angle = -(90 + angle) if angle < -45 else -angle
        if abs(angle) < 1.0 or abs(angle) > 30.0:   # ignore le bruit / sur-rotation
            return gray
        h, w = gray.shape[:2]
        M = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
        return cv2.warpAffine(gray, M, (w, h),
                              flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
    except Exception:
        return gray


def detect_plates(frame: np.ndarray, confidence_threshold: float = 0.45) -> List[Tuple]:
    """
    Détecte les plaques dans la frame.

    Returns:
        Liste de ((x, y, w, h), det_conf). Vide si LPR indisponible ou aucune plaque.
    """
    if not LPR_AVAILABLE or _PLATE_MODEL is None or frame is None or frame.size == 0:
        return []

    global _yolo_half
    h, w = frame.shape[:2]
    out: List[Tuple] = []
    try:
        with _yolo_lock:
            if _yolo_half:
                try:
                    results = _PLATE_MODEL(frame, verbose=False, half=True)[0]
                except Exception as e:
                    # FP16 non supporté ici → on bascule définitivement en FP32.
                    logger.warning(f"[LPR] FP16 désactivé (échec inférence half) : {e}")
                    _yolo_half = False
                    results = _PLATE_MODEL(frame, verbose=False)[0]
            else:
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


def _block_metrics(bbox) -> Tuple[float, float, float]:
    """
    À partir d'un polygone EasyOCR (4 points [[x,y], ...], potentiellement
    incliné), renvoie l'enveloppe alignée sur les axes :
        (x_left, y_center, height)  en pixels.

    On prend min/max sur les 4 sommets → robuste aux boîtes pivotées.
    """
    xs = [float(p[0]) for p in bbox]
    ys = [float(p[1]) for p in bbox]
    x_min, x_max = min(xs), max(xs)
    y_min, y_max = min(ys), max(ys)
    height = max(1.0, y_max - y_min)
    return x_min, (y_min + y_max) / 2.0, height


def _spatial_reading_order(detections: List[Tuple]) -> List[Tuple[str, float]]:
    """
    Ordre de lecture spatial 2D — agnostique du layout (mono-ligne longue OU
    multi-lignes carrée/empilée), sans aucun format pays codé en dur.

    Étape 1 — Filtrage géométrique du bruit (hauteur de police) :
        on calcule la hauteur en pixels de chaque bloc, on prend la hauteur max,
        puis on rejette tout bloc dont la hauteur < 45 % de ce max (élimine les
        petits textes non essentiels : nom de pays, labels structurels…).

    Étape 2 — Regroupement spatial 2D (ordre de lecture multi-lignes) :
        on NE trie PAS bêtement de gauche à droite. On regroupe d'abord les blocs
        en lignes horizontales logiques via le centre vertical (Y) : deux blocs
        qui se chevauchent verticalement (distance entre centres Y < la moitié de
        leur hauteur moyenne) appartiennent à la MÊME ligne. On trie ensuite les
        lignes de HAUT en BAS, et, dans chaque ligne, les blocs de GAUCHE à DROITE.

    Returns:
        Liste ordonnée de (token_normalisé, confiance). Vide si rien d'exploitable.
    """
    # Normalisation + métriques géométriques de chaque bloc OCR.
    blocks = []
    for bbox, txt, conf in detections:
        norm = normalize_plate(txt)            # majuscules + suppr. non-alphanum
        if not norm:
            continue
        x_left, y_center, height = _block_metrics(bbox)
        blocks.append({
            "text": norm, "conf": float(conf),
            "x_left": x_left, "y_center": y_center, "height": height,
        })
    if not blocks:
        return []

    # ── Étape 1 : filtrage par hauteur (≥ 45 % de la hauteur max) ──────────────
    max_h = max(b["height"] for b in blocks)
    height_thresh = _MIN_TEXT_HEIGHT_RATIO * max_h
    blocks = [b for b in blocks if b["height"] >= height_thresh]
    if not blocks:
        return []

    # ── Étape 2 : regroupement 2D en lignes horizontales ──────────────────────
    # On parcourt les blocs du haut vers le bas et on les agrège dans une ligne
    # existante si leurs centres Y se chevauchent (< 0.5 × hauteur moyenne).
    lines: List[Dict] = []
    for b in sorted(blocks, key=lambda bl: bl["y_center"]):
        placed = False
        for ln in lines:
            avg_h = (b["height"] + ln["mean_h"]) / 2.0
            if abs(b["y_center"] - ln["mean_y"]) < 0.5 * avg_h:
                ln["blocks"].append(b)
                n = len(ln["blocks"])
                ln["mean_y"] = sum(x["y_center"] for x in ln["blocks"]) / n
                ln["mean_h"] = sum(x["height"] for x in ln["blocks"]) / n
                placed = True
                break
        if not placed:
            lines.append({"blocks": [b], "mean_y": b["y_center"], "mean_h": b["height"]})

    lines.sort(key=lambda ln: ln["mean_y"])    # lignes : haut → bas
    ordered: List[Tuple[str, float]] = []
    for ln in lines:
        for b in sorted(ln["blocks"], key=lambda bl: bl["x_left"]):   # gauche → droite
            ordered.append((b["text"], b["conf"]))
    return ordered


def read_plate_text(plate_crop: np.ndarray) -> Tuple[str, float]:
    """
    Lit le texte d'un crop de plaque via EasyOCR puis applique l'ordre de lecture
    spatial 2D (cf. _spatial_reading_order) — gère indifféremment les plaques
    mono-ligne et multi-lignes, sans format pays codé en dur.

    NB latence : cette fonction (OCR + assemblage) est volontairement appelée
    depuis le worker OCR de PlateProcessor, JAMAIS depuis le thread caméra, afin
    de ne pas introduire de saccade dans la boucle de tracking vidéo WebRTC.

    Returns:
        (texte_normalisé, confiance_ocr). ("", 0.0) si échec / illisible.
    """
    if not LPR_AVAILABLE or _OCR_READER is None or plate_crop is None or plate_crop.size == 0:
        return "", 0.0

    ocr_input = _preprocess_crop(plate_crop)

    try:
        with _ocr_lock:
            # detail=1 → [(bbox, text, conf), ...]
            detections = _OCR_READER.readtext(
                ocr_input, allowlist=_OCR_ALLOWLIST, detail=1, paragraph=False
            )
    except Exception as e:
        logger.error(f"[LPR] Erreur OCR : {e}")
        return "", 0.0

    if not detections:
        return "", 0.0

    # Étapes 1 & 2 : filtrage hauteur + regroupement spatial multi-lignes.
    ordered = _spatial_reading_order(detections)
    if not ordered:
        return "", 0.0

    # ── Étape 3 : assemblage + validation universelle ─────────────────────────
    # Concaténation séquentielle (ligne 1 g→d, puis ligne 2 g→d, …) puis nettoyage
    # final (majuscules, suppression espaces/non-alphanumérique) — les tokens sont
    # déjà normalisés, on re-nettoie par sûreté.
    plate = _NON_ALNUM.sub("", "".join(t for t, _ in ordered).upper())

    # Validateur permissif : uniquement A-Z et 0-9, longueur 4..10.
    if not _PLATE_VALIDATOR.match(plate):
        return "", 0.0

    confs = [c for _, c in ordered]
    avg_conf = float(np.mean(confs)) if confs else 0.0
    return plate, avg_conf


# Chargement + warm-up au démarrage (après définition de toutes les fonctions
# appelées par le warm-up). Non bloquant : n'échoue jamais "fort".
_load_models()

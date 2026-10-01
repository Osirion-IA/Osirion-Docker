# person_detection.py
"""
Détection de personnes — SEULE couche GPU du Core (une passe YOLO par frame).

Modèle : Ultralytics YOLO (COCO, classe 0 « person »), défaut yolo26n (NMS-free,
edge-optimisé). Singleton chargé UNE fois et partagé entre toutes les caméras,
protégé par un verrou (concurrence CUDA/torch). Dégradation gracieuse : si
ultralytics ou le modèle manquent, `detect_persons` renvoie [] sans jamais
planter le pipeline (les métadonnées continuent d'être publiées, vides).

Sortie de `detect_persons` : liste de [x1, y1, x2, y2, score] (repère de la frame
fournie), directement consommable par l'adaptateur OC-SORT.
"""
import os
import threading
import numpy as np

from utils.logger import get_logger

logger = get_logger(__name__)

# Chemin/nom du modèle. yolo26n.pt est auto-téléchargé par ultralytics au 1er
# usage (ou pré-embarqué dans l'image Docker). Surcharger via PERSON_MODEL_PATH.
_MODEL_PATH = os.getenv("PERSON_MODEL_PATH", "yolo26n.pt")
_PERSON_CLASS = 0  # index COCO de la classe « person »
# Résolution d'inférence (côté long, letterbox). 0/absent → défaut Ultralytics (640).
# La monter améliore le recall des personnes petites/lointaines (coût GPU ~quadratique).
_IMGSZ = int(os.getenv("PERSON_YOLO_IMGSZ", "0")) or None

_MODEL = None
_PRECISION: dict = {}             # kwargs de précision passés à predict() (FP16 ou vide)
_LOCK = threading.Lock()          # sérialise les inférences (contexte CUDA partagé)
_LOAD_LOCK = threading.Lock()     # protège le chargement paresseux
_LOAD_FAILED = False
PERSON_DETECTOR_AVAILABLE = False


def _precision_kwargs(use_half: bool) -> dict:
    """Argument de demi-précision, compatible avec les deux API Ultralytics.

    `half=True` est DÉPRÉCIÉ depuis Ultralytics 8.4 : il fonctionne encore (il est
    réacheminé vers `quantize`) mais journalise un avertissement À CHAQUE inférence,
    ce qui noie les logs du Core (et fait tourner la rotation sur du bruit).
    `quantize=16` est la forme canonique FP16 ; repli sur `half` si l'installation
    est antérieure.
    """
    if not use_half:
        return {}
    try:
        from ultralytics.utils import DEFAULT_CFG_DICT
        if "quantize" in DEFAULT_CFG_DICT:
            return {"quantize": 16}
    except Exception:
        pass
    return {"half": True}


def _load():
    """Charge le modèle une seule fois (paresseux, thread-safe). Renvoie le modèle
    ou None si le chargement échoue (dégradation gracieuse)."""
    global _MODEL, _PRECISION, _LOAD_FAILED, PERSON_DETECTOR_AVAILABLE
    if _MODEL is not None or _LOAD_FAILED:
        return _MODEL
    with _LOAD_LOCK:
        if _MODEL is not None or _LOAD_FAILED:
            return _MODEL
        try:
            import torch
            from ultralytics import YOLO

            model = YOLO(_MODEL_PATH)
            use_half = (
                os.getenv("PERSON_YOLO_HALF", "true").lower() == "true"
                and torch.cuda.is_available()
            )
            precision = _precision_kwargs(use_half)

            # Warm-up : première inférence à vide pour éviter le pic de latence au
            # démarrage (allocation CUDA, compilation des kernels) — à l'imgsz réel.
            dummy = np.zeros((640, 640, 3), dtype=np.uint8)
            _warm_kwargs = {"classes": [_PERSON_CLASS], "verbose": False, **precision}
            if _IMGSZ:
                _warm_kwargs["imgsz"] = _IMGSZ
            model.predict(dummy, **_warm_kwargs)

            _MODEL = model
            _PRECISION = precision
            PERSON_DETECTOR_AVAILABLE = True
            logger.info(
                f"[person] modèle YOLO chargé ({_MODEL_PATH}, "
                f"fp16={bool(precision)}, imgsz={_IMGSZ or 'défaut(640)'})."
            )
        except Exception as e:
            _LOAD_FAILED = True
            PERSON_DETECTOR_AVAILABLE = False
            logger.error(
                f"[person] chargement impossible du modèle '{_MODEL_PATH}' — "
                f"détection désactivée (les métadonnées restent publiées) : {e}"
            )
    return _MODEL


def detect_persons(frame, confidence_threshold: float = 0.4,
                   imgsz_override: int = None):
    """Détecte les personnes dans `frame`.

    Renvoie une liste de [x1, y1, x2, y2, score] (float). ``imgsz_override``
    permet au pipeline d'alterner les échelles pour les caméras de présence sans
    charger un second modèle ni lancer deux inférences sur la même frame. Liste
    vide si aucune personne, si le modèle manque ou en cas d'erreur d'inférence.
    """
    model = _MODEL or _load()
    if model is None:
        return []
    try:
        predict_kwargs = {
            "classes": [_PERSON_CLASS],
            "conf": confidence_threshold,
            "verbose": False,
            **_PRECISION,
        }
        effective_imgsz = int(imgsz_override) if imgsz_override else _IMGSZ
        if effective_imgsz:
            predict_kwargs["imgsz"] = effective_imgsz
        with _LOCK:
            results = model.predict(frame, **predict_kwargs)
    except Exception as e:
        logger.error(f"[person] inférence échouée : {e}")
        return []

    out = []
    for r in results:
        boxes = getattr(r, "boxes", None)
        if boxes is None or boxes.xyxy is None:
            continue
        xyxy = boxes.xyxy.cpu().numpy()
        conf = boxes.conf.cpu().numpy()
        for (x1, y1, x2, y2), c in zip(xyxy, conf):
            out.append([float(x1), float(y1), float(x2), float(y2), float(c)])
    return out

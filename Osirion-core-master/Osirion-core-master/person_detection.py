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

_MODEL = None
_HALF = False
_LOCK = threading.Lock()          # sérialise les inférences (contexte CUDA partagé)
_LOAD_LOCK = threading.Lock()     # protège le chargement paresseux
_LOAD_FAILED = False
PERSON_DETECTOR_AVAILABLE = False


def _load():
    """Charge le modèle une seule fois (paresseux, thread-safe). Renvoie le modèle
    ou None si le chargement échoue (dégradation gracieuse)."""
    global _MODEL, _HALF, _LOAD_FAILED, PERSON_DETECTOR_AVAILABLE
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
            # Warm-up : première inférence à vide pour éviter le pic de latence au
            # démarrage (allocation CUDA, compilation des kernels).
            dummy = np.zeros((640, 640, 3), dtype=np.uint8)
            model.predict(dummy, classes=[_PERSON_CLASS], half=use_half, verbose=False)

            _MODEL = model
            _HALF = use_half
            PERSON_DETECTOR_AVAILABLE = True
            logger.info(f"[person] modèle YOLO chargé ({_MODEL_PATH}, half={use_half}).")
        except Exception as e:
            _LOAD_FAILED = True
            PERSON_DETECTOR_AVAILABLE = False
            logger.error(
                f"[person] chargement impossible du modèle '{_MODEL_PATH}' — "
                f"détection désactivée (les métadonnées restent publiées) : {e}"
            )
    return _MODEL


def detect_persons(frame, confidence_threshold: float = 0.4):
    """Détecte les personnes dans `frame`.

    Renvoie une liste de [x1, y1, x2, y2, score] (float). Liste vide si aucune
    personne, si le modèle n'a pas pu être chargé, ou en cas d'erreur d'inférence.
    """
    model = _MODEL or _load()
    if model is None:
        return []
    try:
        with _LOCK:
            results = model.predict(
                frame,
                classes=[_PERSON_CLASS],
                conf=confidence_threshold,
                half=_HALF,
                verbose=False,
            )
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

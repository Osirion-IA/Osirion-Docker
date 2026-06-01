import cv2
import numpy as np
import onnxruntime as ort
from insightface.app import FaceAnalysis
from typing import List, Tuple, Optional
from utils.logger import get_logger

logger = get_logger(__name__)

# ── Vérification GPU au démarrage ──────────────────────────────────────────
_available_providers = ort.get_available_providers()
logger.info(f"ONNX Runtime — providers disponibles : {_available_providers}")

_use_gpu = 'CUDAExecutionProvider' in _available_providers
if _use_gpu:
    logger.info("GPU détecté : InsightFace utilisera CUDAExecutionProvider (RTX 4050)")
else:
    logger.warning(
        "CUDAExecutionProvider absent — InsightFace tournera sur CPU. "
        "Vérifiez que nvidia-container-toolkit est installé et que le conteneur "
        "est lancé avec --gpus ou le champ 'deploy.resources' dans docker-compose."
    )

_providers = ['CUDAExecutionProvider', 'CPUExecutionProvider'] if _use_gpu else ['CPUExecutionProvider']

app = FaceAnalysis(
    name='buffalo_l',
    providers=_providers,
    allowed_modules=['detection', 'recognition']
)
app.prepare(ctx_id=0 if _use_gpu else -1, det_size=(640, 640))

# Confirmer quel provider est réellement actif sur chaque modèle
for _model_name, _model in app.models.items():
    _session = getattr(_model, 'session', None)
    if _session is not None:
        _active = _session.get_providers()[0]
        logger.info(f"  InsightFace [{_model_name}] → {_active}")


def detect_faces_with_embeddings(
    frame: np.ndarray,
    confidence_threshold: float = 0.7
) -> Tuple[np.ndarray, List[Tuple]]:
    """
    Single GPU pass: face detection + 5-point alignment + ArcFace 512D embedding.

    Returns:
        frame_annotated: copy of frame with bounding boxes drawn
        faces: list of ((x, y, w, h), confidence, embedding_512d)
    """
    if frame is None or frame.size == 0:
        return frame, []

    frame_annotated = frame.copy()
    h, w = frame.shape[:2]
    faces_out = []

    for face in app.get(frame):
        if float(face.det_score) < confidence_threshold:
            continue

        x1, y1, x2, y2 = face.bbox.astype(int)
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)

        conf = float(face.det_score)

        # Normalisation L2 défensive : garantit norme=1.0 pour IndexFlatIP (cosine exact).
        # InsightFace normalise déjà, mais une re-normalisation explicite coûte ~1µs
        # et élimine tout risque de drift numérique entre GPU et CPU providers.
        raw_emb = face.embedding.astype(np.float32)
        norm = np.linalg.norm(raw_emb)
        embedding = raw_emb / norm if norm > 0 else raw_emb

        faces_out.append(((x1, y1, x2 - x1, y2 - y1), conf, embedding))

    return frame_annotated, faces_out

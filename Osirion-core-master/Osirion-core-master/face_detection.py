import cv2
import numpy as np
import onnxruntime as ort
import threading
import queue
from insightface.app import FaceAnalysis
from insightface.app.common import Face
from typing import List, Tuple, Optional
from utils.logger import get_logger

logger = get_logger(__name__)

# ── Configuration (repli sûr si la config manque) ───────────────────────────
def _cfg(name, default):
    try:
        from config import settings
        return getattr(settings, name, default)
    except Exception:
        return default

_MODEL_PACK = _cfg('INSIGHTFACE_MODEL_PACK', 'antelopev2')
_DET_SIZE = _cfg('FACE_DET_SIZE', (640, 640))
_CLAHE_ENABLED = _cfg('FACE_CLAHE_ENABLED', True)
_CLAHE_CLIP = float(_cfg('FACE_CLAHE_CLIP', 2.0))

_INTRA_OP = int(_cfg('ONNX_INTRA_OP_THREADS', 4))
_INTER_OP = int(_cfg('ONNX_INTER_OP_THREADS', 2))
_GPU_MEM_LIMIT = int(float(_cfg('ONNX_GPU_MEM_LIMIT_GB', 2)) * 1024 * 1024 * 1024)
_ARENA_STRATEGY = _cfg('ONNX_ARENA_EXTEND_STRATEGY', 'kNextPowerOfTwo')
_CUDNN_ALGO = _cfg('ONNX_CUDNN_CONV_ALGO', 'EXHAUSTIVE')
_TRT_FP16 = bool(_cfg('FACE_TRT_FP16', False))
_TRT_CACHE_DIR = _cfg('ONNX_TRT_CACHE_DIR', '/tmp/trt_cache')

_USE_WORKER = bool(_cfg('FACE_INFERENCE_WORKER', True))
_N_WORKERS = max(1, int(_cfg('FACE_INFERENCE_WORKERS', 1)))
_INFER_TIMEOUT = float(_cfg('FACE_INFER_TIMEOUT', 10.0))

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


# ────────────────────────────────────────────────────────────────────────────
# Construction des sessions ONNX optimisées (SessionOptions + provider_options)
# ────────────────────────────────────────────────────────────────────────────
def _build_providers() -> Tuple[list, list]:
    """Listes (providers, provider_options) ALIGNÉES pour onnxruntime.

    InsightFace ne transmet QUE providers + provider_options à InferenceSession
    (pas les SessionOptions). On gère donc les SessionOptions séparément en
    reconstruisant les sessions (cf. _apply_session_options)."""
    if not _use_gpu:
        return ['CPUExecutionProvider'], [{}]

    cuda_opts = {
        'device_id': 0,
        'arena_extend_strategy': _ARENA_STRATEGY,
        'gpu_mem_limit': _GPU_MEM_LIMIT,
        'cudnn_conv_algo_search': _CUDNN_ALGO,
        'do_copy_in_default_stream': True,
    }
    providers: list = []
    provider_options: list = []

    # FP16 réel uniquement via TensorRT EP (le CUDA EP n'a pas d'option FP16).
    if _TRT_FP16 and 'TensorrtExecutionProvider' in _available_providers:
        import os as _os
        _os.makedirs(_TRT_CACHE_DIR, exist_ok=True)
        providers.append('TensorrtExecutionProvider')
        provider_options.append({
            'device_id': 0,
            'trt_fp16_enable': True,
            'trt_engine_cache_enable': True,
            'trt_engine_cache_path': _TRT_CACHE_DIR,
        })
        logger.info("TensorRT FP16 activé (1er build de moteur potentiellement long).")

    providers += ['CUDAExecutionProvider', 'CPUExecutionProvider']
    provider_options += [cuda_opts, {}]
    return providers, provider_options


def _build_session_options() -> ort.SessionOptions:
    so = ort.SessionOptions()
    so.intra_op_num_threads = _INTRA_OP
    so.inter_op_num_threads = _INTER_OP
    so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    return so


def _apply_session_options(app: FaceAnalysis, providers: list, provider_options: list) -> None:
    """Reconstruit chaque session de modèle AVEC nos SessionOptions.

    insightface crée ses sessions sans exposer les SessionOptions (threads). On
    remplace donc `model.session` par une session équivalente (même fichier .onnx,
    donc mêmes noms d'E/S) configurée avec intra/inter_op_num_threads. Best-effort :
    en cas d'échec on conserve la session d'origine (jamais de panne)."""
    so = _build_session_options()
    for name, model in app.models.items():
        model_file = getattr(model, 'model_file', None)
        if model_file is None or getattr(model, 'session', None) is None:
            continue
        try:
            model.session = ort.InferenceSession(
                model_file, sess_options=so,
                providers=providers, provider_options=provider_options,
            )
        except Exception as exc:
            logger.warning(
                f"SessionOptions non appliquées sur le modèle [{name}] "
                f"(session d'origine conservée) : {exc}"
            )


def _build_app() -> FaceAnalysis:
    """Instancie + prépare un FaceAnalysis optimisé (1 session par modèle)."""
    providers, provider_options = _build_providers()
    app = FaceAnalysis(
        name=_MODEL_PACK,
        providers=providers,
        provider_options=provider_options,
        allowed_modules=['detection', 'recognition'],
    )
    app.prepare(ctx_id=0 if _use_gpu else -1, det_size=_DET_SIZE)
    _apply_session_options(app, providers, provider_options)
    for name, model in app.models.items():
        sess = getattr(model, 'session', None)
        if sess is not None:
            logger.info(f"  InsightFace [{_MODEL_PACK}/{name}] → {sess.get_providers()[0]}")
    return app


# ────────────────────────────────────────────────────────────────────────────
# Worker d'inférence — exécute SCRFD + CLAHE + ArcFace (propriétaire du GPU)
# ────────────────────────────────────────────────────────────────────────────
class _InferenceWorker:
    """Détenteur d'UNE session FaceAnalysis + son CLAHE. Exécute la détection,
    la normalisation CLAHE et l'extraction ArcFace. Utilisé soit en direct
    (worker désactivé), soit possédé par un thread consommateur de la file."""

    def __init__(self, app: FaceAnalysis):
        self.app = app
        self.det = app.models.get('detection')
        self.rec = app.models.get('recognition')
        self.clahe = (cv2.createCLAHE(clipLimit=_CLAHE_CLIP, tileGridSize=(8, 8))
                      if _CLAHE_ENABLED else None)

    def _apply_clahe_lab(self, img: np.ndarray) -> np.ndarray:
        """CLAHE sur le canal L (LAB) → retour BGR (géométrie inchangée)."""
        lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        l = self.clahe.apply(l)
        return cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)

    def process(self, frame: np.ndarray) -> list:
        """Détection + embedding ArcFace, CLAHE appliqué AVANT l'extraction.

        On détecte sur la frame d'origine (kps fiables), on calcule UNE image
        rehaussée CLAHE, puis on extrait l'embedding de chaque visage sur cette
        image (ré-alignement 5-points → crop CLAHE envoyé à ArcFace). La
        reconnaissance n'est exécutée qu'UNE fois. Repli sûr sur app.get() (sans
        CLAHE) si quoi que ce soit échoue → aucune panne."""
        if self.clahe is not None and self.rec is not None and self.det is not None:
            try:
                bboxes, kpss = self.det.detect(frame, max_num=0, metric='default')
                if bboxes is None or bboxes.shape[0] == 0:
                    return []
                enhanced = self._apply_clahe_lab(frame)
                faces = []
                for i in range(bboxes.shape[0]):
                    kps = kpss[i] if kpss is not None else None
                    face = Face(bbox=bboxes[i, 0:4], kps=kps, det_score=float(bboxes[i, 4]))
                    self.rec.get(enhanced, face)   # remplit face.embedding (crop CLAHE aligné)
                    faces.append(face)
                return faces
            except Exception as exc:
                logger.warning(f"Chemin CLAHE en échec — repli app.get() sans CLAHE : {exc}")
        return self.app.get(frame)


class _InferenceEngine:
    """Moteur d'inférence faciale partagé par toutes les caméras.

    Mode worker (défaut) : un pool de threads consomme une file de requêtes ; les
    threads caméra SOUMETTENT une frame et ATTENDENT le résultat. Avantages :
      · accès GPU sérialisé sur un propriétaire unique (contexte CUDA stable) ;
      · 1 session partagée (pool=1, ~1 GB) → mémoire prévisible, ou N sessions
        propres (pool>1) pour monter en débit au prix de la VRAM ;
      · les boucles de tracking ne se disputent plus la même session sous le GIL.

    Mode direct (FACE_INFERENCE_WORKER=false) : appel synchrone sur le thread
    appelant via une session partagée (comportement Sprint 1).
    """

    def __init__(self):
        self._jobs: "queue.Queue" = queue.Queue()
        self._stop = threading.Event()
        self._threads: List[threading.Thread] = []
        self._workers: List[_InferenceWorker] = []
        self._direct: Optional[_InferenceWorker] = None

        if not _USE_WORKER:
            self._direct = _InferenceWorker(_build_app())
            logger.info("Moteur d'inférence : mode DIRECT (session partagée, sans worker).")
            return

        # pool=1 → une seule app partagée par l'unique worker.
        # pool>1 → une app (session) PROPRE par worker (pas d'accès concurrent à
        #          la même session ORT).
        shared_app = _build_app() if _N_WORKERS == 1 else None
        for i in range(_N_WORKERS):
            worker = _InferenceWorker(shared_app if shared_app is not None else _build_app())
            self._workers.append(worker)
            t = threading.Thread(
                target=self._loop, args=(worker,),
                name=f"face-inference-{i}", daemon=True,
            )
            t.start()
            self._threads.append(t)
        logger.info(
            f"Moteur d'inférence : {_N_WORKERS} worker(s) "
            f"({'session partagée' if _N_WORKERS == 1 else 'session par worker'}), "
            f"pack={_MODEL_PACK}, det_size={_DET_SIZE}."
        )

    def _loop(self, worker: _InferenceWorker) -> None:
        while not self._stop.is_set():
            try:
                req = self._jobs.get(timeout=0.5)
            except queue.Empty:
                continue
            if req is None:   # sentinelle d'arrêt
                break
            try:
                req["faces"] = worker.process(req["frame"])
            except Exception as exc:
                req["err"] = exc
                req["faces"] = []
            finally:
                req["event"].set()

    def infer(self, frame: np.ndarray) -> list:
        """Soumet une frame et renvoie la liste de visages (bloque jusqu'au résultat).

        Repli direct si le worker est désactivé/mort → ne bloque jamais
        indéfiniment (garde-fou de timeout)."""
        if not _USE_WORKER or self._direct is not None:
            return self._direct.process(frame) if self._direct else []
        if not any(t.is_alive() for t in self._threads):
            # Pool mort (ne devrait pas arriver) : repli synchrone via un worker.
            if self._workers:
                return self._workers[0].process(frame)
            return []
        req = {"frame": frame, "faces": None, "err": None, "event": threading.Event()}
        self._jobs.put(req)
        if not req["event"].wait(_INFER_TIMEOUT):
            logger.error(
                f"Inférence faciale : timeout (> {_INFER_TIMEOUT:.0f}s) — frame ignorée."
            )
            return []
        return req["faces"] or []

    def summary(self) -> str:
        if not _USE_WORKER:
            mode = "direct (session partagée)"
        else:
            mode = (f"{_N_WORKERS} worker(s), "
                    f"{'1 session partagée' if _N_WORKERS == 1 else f'{_N_WORKERS} sessions'}")
        return (f"pack={_MODEL_PACK} det_size={_DET_SIZE} mode={mode} "
                f"intra_op={_INTRA_OP} inter_op={_INTER_OP} "
                f"gpu_mem_limit={_GPU_MEM_LIMIT // (1024*1024)}MB "
                f"cudnn={_CUDNN_ALGO} trt_fp16={_TRT_FP16}")

    def shutdown(self) -> None:
        """Arrêt propre des threads d'inférence (idempotent)."""
        self._stop.set()
        for _ in self._threads:
            try:
                self._jobs.put_nowait(None)
            except Exception:
                pass
        for t in self._threads:
            if t.is_alive():
                t.join(timeout=5)


# Singleton créé à l'import (les modèles se chargent une fois pour tout le process).
_engine = _InferenceEngine()
logger.info(f"InsightFace prêt — {_engine.summary()}")


def get_inference_engine() -> "_InferenceEngine":
    """Accès au moteur d'inférence partagé (lifecycle géré par SurveillanceSystem)."""
    return _engine


def _frontality_from_kps(kps) -> float:
    """Score de frontalité ∈ [0,1] à partir des 5 points SCRFD (gratuit, sans
    modèle de pose). 1.0 = visage frontal ; → 0 = profil extrême.

    Mesure la symétrie horizontale nez↔yeux : un lacet (yaw) rapproche le nez
    d'un œil et éloigne l'autre. Le score est un RATIO (min/max des distances
    nez-œil) → indépendant de la taille du visage / de la résolution. Sert à NE
    PAS reconnaître les profils, où l'embedding ArcFace se dégrade fortement.

    kps : ndarray (5,2) = [œil_g, œil_d, nez, bouche_g, bouche_d] (repère image).
    Retourne 1.0 (neutre, aucune pénalité) si les points sont indisponibles.
    """
    if kps is None or len(kps) < 3:
        return 1.0
    try:
        left_eye_x = float(kps[0][0])
        right_eye_x = float(kps[1][0])
        nose_x = float(kps[2][0])
    except (TypeError, IndexError, ValueError):
        return 1.0
    d_left = abs(nose_x - left_eye_x)
    d_right = abs(right_eye_x - nose_x)
    hi = max(d_left, d_right)
    if hi <= 1e-6:
        return 0.0
    return max(0.0, min(1.0, min(d_left, d_right) / hi))


def detect_faces_with_embeddings(
    frame: np.ndarray,
    confidence_threshold: float = 0.7
) -> Tuple[np.ndarray, List[Tuple]]:
    """
    Détection visage + alignement 5-points + embedding ArcFace 512D.

    L'inférence GPU (SCRFD + CLAHE + ArcFace) est déléguée au moteur d'inférence
    partagé (worker dédié) ; le post-traitement léger (clip bbox, L2, frontalité)
    reste sur le thread appelant.

    Returns:
        frame_ref: la frame d'entrée telle quelle (compat. de signature ; AUCUNE
                   copie, aucun dessin — le seul appelant ignore cette valeur)
        faces: liste de ((x, y, w, h), confidence, embedding_512d, frontality)
               frontality ∈ [0,1] (1=frontal) — exploité par le gate qualité du
               TrackingProcessor pour ignorer les profils extrêmes.
    """
    if frame is None or frame.size == 0:
        return frame, []

    # Pas de copie : on renvoyait autrefois frame.copy() pour y dessiner les
    # annotations, mais l'overlay se fait désormais côté client (WebRTC) et le
    # SEUL appelant ignore cette valeur (`_, faces_data = ...`). Copier une frame
    # ~1280×720×3 (~2,6 Mo) à CHAQUE frame traitée × N caméras était du gaspillage.
    h, w = frame.shape[:2]
    faces_out = []

    for face in _engine.infer(frame):
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

        frontality = _frontality_from_kps(getattr(face, 'kps', None))

        faces_out.append(((x1, y1, x2 - x1, y2 - y1), conf, embedding, frontality))

    return frame, faces_out

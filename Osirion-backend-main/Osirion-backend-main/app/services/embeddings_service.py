import cv2
import time
import numpy as np
import logging
from insightface.app import FaceAnalysis
from typing import Optional

logger = logging.getLogger(__name__)

# Pipeline identique au Core :
#   - buffalo_l   → SCRFD (détection) + ArcFace 512D (reconnaissance)
#   - det_size=(640,640) → même résolution de détection que le Core → même qualité d'alignement
#   - CPU pour le backend (uploads peu fréquents, évite la contention GPU avec le Core)
_app = FaceAnalysis(
    name='buffalo_l',
    providers=['CPUExecutionProvider'],
    allowed_modules=['detection', 'recognition']
)
_app.prepare(ctx_id=-1, det_size=(640, 640))

_MAX_CENTROID_IMAGES = 5


# ─────────────────────────────────────────────────────────────────────────────
# Primitives internes
# ─────────────────────────────────────────────────────────────────────────────

def _l2_normalize(emb: np.ndarray) -> np.ndarray:
    norm = np.linalg.norm(emb)
    return emb / norm if norm > 0 else emb


# ─────────────────────────────────────────────────────────────────────────────
# Augmentation (CAS 1 : image unique)
# ─────────────────────────────────────────────────────────────────────────────

def generate_augmented_images(image: np.ndarray) -> list:
    """
    Génère 4 variantes légères d'une image d'enrollment.

    Appliquées avant la détection InsightFace : SCRFD ré-effectue son propre
    alignement 5-points sur chaque variante → embeddings cohérents et indépendants.

    Transformations autorisées (non déformantes) :
      - flip horizontal     (symétrie ArcFace)
      - rotation ±7°        (inclinaisons naturelles de tête)
      - luminosité +15%     (variation d'éclairage légère)
    """
    h, w = image.shape[:2]
    center = (w // 2, h // 2)
    variants = []

    # Flip horizontal
    variants.append(cv2.flip(image, 1))

    # Rotation +7°
    M_pos = cv2.getRotationMatrix2D(center, 7.0, 1.0)
    variants.append(
        cv2.warpAffine(image, M_pos, (w, h), borderMode=cv2.BORDER_REFLECT_101)
    )

    # Rotation −7°
    M_neg = cv2.getRotationMatrix2D(center, -7.0, 1.0)
    variants.append(
        cv2.warpAffine(image, M_neg, (w, h), borderMode=cv2.BORDER_REFLECT_101)
    )

    # Luminosité +15 % (canal V dans HSV — évite la saturation des canaux RGB)
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV).astype(np.float32)
    hsv[:, :, 2] = np.clip(hsv[:, :, 2] * 1.15, 0, 255)
    variants.append(cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR))

    return variants  # toujours 4 éléments


# ─────────────────────────────────────────────────────────────────────────────
# Centroid
# ─────────────────────────────────────────────────────────────────────────────

def compute_centroid_embedding(embeddings: list) -> np.ndarray:
    """
    Moyenne de N embeddings L2-normalisés, puis re-normalisation finale.

    Propriété : le centroid de vecteurs unitaires n'est pas unitaire → la
    re-normalisation est obligatoire pour garantir norme=1.0 (IndexFlatIP).
    """
    centroid = np.stack(embeddings, axis=0).mean(axis=0)
    return _l2_normalize(centroid)


# ─────────────────────────────────────────────────────────────────────────────
# Enrollment hybride (point d'entrée principal)
# ─────────────────────────────────────────────────────────────────────────────

def enroll_from_images(
    images: list,
    confidence_threshold: float = 0.85,
    blur_threshold: float = 60.0,
) -> Optional[tuple]:
    """
    Enrollment hybride :

    CAS 1 — 1 image  → génère 4 variantes augmentées → centroid sur les embeddings valides
    CAS 2 — ≥ 2 images → pas d'augmentation → centroid direct (max _MAX_CENTROID_IMAGES)

    Filtres qualité appliqués sur chaque candidat :
      - Variance Laplacienne ≥ blur_threshold  (0 = filtre désactivé)
      - Score de détection SCRFD ≥ confidence_threshold

    Returns:
        (centroid_as_list_512d, face_crop_ndarray)  si au moins 1 embedding valide
        None                                         sinon
    """
    if not images:
        return None

    t0 = time.perf_counter()
    use_augmentation = len(images) < 2

    if use_augmentation:
        source = images[0]
        candidates = [source] + generate_augmented_images(source)
        logger.info(
            f"Enrollment hybride (CAS 1) : 1 image source → "
            f"{len(candidates)} candidats (original + {len(candidates) - 1} augmentations)"
        )
    else:
        candidates = images[:_MAX_CENTROID_IMAGES]
        logger.info(
            f"Enrollment hybride (CAS 2) : {len(candidates)} images "
            f"(pas d'augmentation, centroid direct)"
        )

    embeddings: list = []
    best_face_crop: Optional[np.ndarray] = None
    n_blurry = n_no_face = n_low_conf = 0

    for i, img in enumerate(candidates):
        if img is None or img.size == 0:
            continue

        # ── Filtre flou ───────────────────────────────────────────────────
        if blur_threshold > 0:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
            if sharpness < blur_threshold:
                n_blurry += 1
                logger.debug(
                    f"  Image[{i}] ignorée — Laplacien={sharpness:.1f} < {blur_threshold}"
                )
                continue

        # ── Détection + embedding SCRFD/ArcFace ──────────────────────────
        try:
            faces = _app.get(img)
        except Exception:
            logger.debug(f"  Image[{i}] — erreur InsightFace (skip)")
            continue

        if not faces:
            n_no_face += 1
            logger.debug(f"  Image[{i}] — aucun visage détecté")
            continue

        best = max(faces, key=lambda f: f.det_score)
        if float(best.det_score) < confidence_threshold:
            n_low_conf += 1
            logger.debug(
                f"  Image[{i}] — score SCRFD={best.det_score:.3f} < {confidence_threshold}"
            )
            continue

        emb = _l2_normalize(best.embedding.copy().astype(np.float32))
        embeddings.append(emb)

        # Crop depuis la première image valide (original en CAS 1, première bonne en CAS 2)
        if best_face_crop is None:
            h, w = img.shape[:2]
            x1, y1, x2, y2 = best.bbox.astype(int)
            best_face_crop = img[max(0, y1):min(h, y2), max(0, x1):min(w, x2)]

    n_valid = len(embeddings)
    n_aug_used = max(0, n_valid - 1) if use_augmentation else 0

    logger.info(
        f"Enrollment : {n_valid}/{len(candidates)} embeddings valides "
        f"(blurry={n_blurry}, no_face={n_no_face}, low_conf={n_low_conf}, "
        f"augmentations_contribuant={n_aug_used})"
    )

    if not embeddings:
        logger.warning(
            "Enrollment échoué : aucun embedding valide après filtrage. "
            f"(confidence≥{confidence_threshold}, Laplacian≥{blur_threshold})"
        )
        return None

    centroid = compute_centroid_embedding(embeddings)
    final_norm = float(np.linalg.norm(centroid))
    elapsed_ms = (time.perf_counter() - t0) * 1000

    logger.info(
        f"Centroid calculé : n_embeddings={n_valid}, dim=512, "
        f"norm={final_norm:.6f}, durée={elapsed_ms:.1f}ms"
    )

    return centroid.tolist(), best_face_crop


# ─────────────────────────────────────────────────────────────────────────────
# API legacy (conservée pour rétrocompatibilité — préférer enroll_from_images)
# ─────────────────────────────────────────────────────────────────────────────

def detect_and_embed(
    image: np.ndarray,
    confidence_threshold: float = 0.7
) -> Optional[tuple]:
    """
    Passe unique : détection SCRFD + alignement + embedding ArcFace.

    Gardée pour les tests existants et les usages hors-enrollment.
    Pour l'enrollment, utiliser enroll_from_images() qui calcule un centroid.
    """
    if image is None or image.size == 0:
        return None

    try:
        faces = _app.get(image)
    except Exception:
        logger.exception("Erreur InsightFace lors du detect_and_embed")
        return None

    if not faces:
        return None

    best_face = max(faces, key=lambda f: f.det_score)
    if float(best_face.det_score) < confidence_threshold:
        return None

    h, w = image.shape[:2]
    x1, y1, x2, y2 = best_face.bbox.astype(int)
    face_crop = image[max(0, y1):min(h, y2), max(0, x1):min(w, x2)]

    emb = best_face.embedding.copy().astype(np.float32)
    norm = np.linalg.norm(emb)
    if norm > 0:
        emb = emb / norm
    logger.debug(
        f"detect_and_embed : norme avant={np.linalg.norm(best_face.embedding):.6f}, "
        f"après={np.linalg.norm(emb):.6f}"
    )
    return emb.tolist(), face_crop

import os
# albumentations (tiré par insightface) tente un check de version en ligne à
# l'import → échoue hors-ligne. Désactivé AVANT d'importer insightface.
os.environ.setdefault("NO_ALBUMENTATIONS_UPDATE", "1")
import cv2
import time
import numpy as np
import logging
from insightface.app import FaceAnalysis
from typing import Optional

logger = logging.getLogger(__name__)

# Pipeline identique au Core — PARITÉ DE MODÈLE OBLIGATOIRE :
#   - pack lu depuis INSIGHTFACE_MODEL_PACK (défaut 'antelopev2' = SCRFD + glintr100
#     ResNet-100). Le Core (face_detection.py) lit la MÊME variable. Un pack
#     différent ici produirait une galerie incompatible avec les requêtes du Core
#     (espaces d'embedding distincts → aucune correspondance).
#   - det_size=(640,640) → même résolution de détection que le Core → même qualité d'alignement
#   - CPU pour le backend (uploads peu fréquents, évite la contention GPU avec le Core)
_MODEL_PACK = os.getenv('INSIGHTFACE_MODEL_PACK', 'antelopev2')
_app = FaceAnalysis(
    name=_MODEL_PACK,
    providers=['CPUExecutionProvider'],
    allowed_modules=['detection', 'recognition']
)
_app.prepare(ctx_id=-1, det_size=(640, 640))
logger.info(f"Enrôlement : pack InsightFace='{_MODEL_PACK}' (CPU)")

_MAX_CENTROID_IMAGES = 5

# ── Seuils qualité de l'enrôlement (tunables via l'environnement) ────────────
# NB : l'enrôlement ne doit JAMAIS être plus strict que la reconnaissance en
# production (le Core détecte à 0.7). Un seuil d'enrôlement à 0.85 rejetait des
# photos parfaitement exploitables → défaut abaissé à 0.6.
_ENROLL_MIN_CONF = float(os.getenv('ENROLL_FACE_MIN_CONFIDENCE', '0.6'))
# Netteté mesurée sur le CROP du visage (pas la frame entière) — voir le loop.
# 0 = filtre désactivé. 25 = valeur conservatrice alignée sur le Core
# (FACE_CROP_MIN_SHARPNESS). L'ancien 60 sur frame entière rejetait à tort les
# portraits à fond flou/bokeh (variance globale faible, visage pourtant net).
_ENROLL_CROP_MIN_SHARP = float(os.getenv('ENROLL_FACE_CROP_MIN_SHARPNESS', '25.0'))


def format_enroll_diagnostics(diag: dict) -> str:
    """Message humain expliquant POURQUOI l'enrôlement n'a produit aucun vecteur.

    Alimenté par le dict `diagnostics` rempli par enroll_from_images(). Permet de
    renvoyer au frontend la cause RÉELLE (pas de visage / confiance trop basse /
    trop flou) au lieu d'un message générique."""
    if not diag:
        return "aucun candidat exploitable"
    parts = []
    if diag.get("n_no_face"):
        parts.append(f"{diag['n_no_face']} image(s) sans visage détecté")
    if diag.get("n_low_conf"):
        parts.append(
            f"{diag['n_low_conf']} visage(s) sous le seuil de confiance "
            f"(meilleur score={diag.get('max_det_score', 0.0):.2f}, "
            f"requis ≥ {diag.get('confidence_threshold', 0.0):.2f})"
        )
    if diag.get("n_blurry"):
        parts.append(
            f"{diag['n_blurry']} visage(s) trop flou(s) "
            f"(meilleure netteté crop={diag.get('max_crop_sharpness', 0.0):.0f}, "
            f"requis ≥ {diag.get('blur_threshold', 0.0):.0f})"
        )
    return " ; ".join(parts) if parts else "aucun candidat exploitable"


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
    confidence_threshold: float = _ENROLL_MIN_CONF,
    blur_threshold: float = _ENROLL_CROP_MIN_SHARP,
    diagnostics: Optional[dict] = None,
) -> Optional[tuple]:
    """
    Enrollment MULTI-VECTEURS (plus de centroïde moyenné).

    CAS 1 — 1 image  → génère 4 variantes augmentées → 1 vecteur par variante valide
    CAS 2 — ≥ 2 images → pas d'augmentation → 1 vecteur par image valide (max _MAX_CENTROID_IMAGES)

    Le moyennage en un centroïde unique est SUPPRIMÉ : il diluait les angles et
    l'éclairage en un point « flou ». On conserve désormais CHAQUE vecteur 512-D
    valide ; ils seront stockés en lignes séparées (table person_embeddings) et la
    recherche fera du max-cosine par personne.

    Filtres qualité appliqués sur chaque candidat (dans l'ordre) :
      - Score de détection SCRFD ≥ confidence_threshold
      - Variance Laplacienne du CROP ≥ blur_threshold  (0 = filtre désactivé)
        → mesurée sur le crop du visage, PAS sur la frame entière : un portrait
          à fond flou/bokeh a une variance globale faible même quand le visage
          est net (faux rejet évité).

    Args:
        diagnostics: dict optionnel rempli en place avec le détail des rejets
            (n_no_face / n_low_conf / n_blurry, meilleurs scores) — utilisé par
            l'appelant pour un message d'erreur précis via format_enroll_diagnostics().

    Returns:
        (list_of_embeddings_512d, face_crop_ndarray)  si ≥ 1 embedding valide
            où list_of_embeddings_512d = List[List[float]] (chaque élément normalisé L2)
        None                                            sinon
    """
    if diagnostics is None:
        diagnostics = {}
    diagnostics.update({
        "n_candidates": 0, "n_valid": 0, "n_blurry": 0, "n_no_face": 0,
        "n_low_conf": 0, "max_det_score": 0.0, "max_crop_sharpness": 0.0,
        "confidence_threshold": confidence_threshold, "blur_threshold": blur_threshold,
    })

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
    max_det_score = 0.0
    max_crop_sharpness = 0.0

    for i, img in enumerate(candidates):
        if img is None or img.size == 0:
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
        det = float(best.det_score)
        max_det_score = max(max_det_score, det)
        if det < confidence_threshold:
            n_low_conf += 1
            logger.debug(
                f"  Image[{i}] — score SCRFD={det:.3f} < {confidence_threshold}"
            )
            continue

        # ── Crop du visage ────────────────────────────────────────────────
        h, w = img.shape[:2]
        x1, y1, x2, y2 = best.bbox.astype(int)
        crop = img[max(0, y1):min(h, y2), max(0, x1):min(w, x2)]

        # ── Filtre de netteté CIBLÉ sur le CROP (pas la frame entière) ──────
        # Une frame entière avec fond flou/bokeh a une variance globale faible
        # même quand le visage est net → mesurer sur le crop évite ce faux rejet.
        if blur_threshold > 0 and crop.size > 0:
            gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
            sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
            max_crop_sharpness = max(max_crop_sharpness, sharpness)
            if sharpness < blur_threshold:
                n_blurry += 1
                logger.debug(
                    f"  Image[{i}] ignorée — netteté crop={sharpness:.1f} < {blur_threshold}"
                )
                continue

        emb = _l2_normalize(best.embedding.copy().astype(np.float32))
        embeddings.append(emb)

        # Crop depuis la première image valide (original en CAS 1, première bonne en CAS 2)
        if best_face_crop is None:
            best_face_crop = crop

    n_valid = len(embeddings)
    n_aug_used = max(0, n_valid - 1) if use_augmentation else 0

    diagnostics.update({
        "n_candidates": len(candidates), "n_valid": n_valid, "n_blurry": n_blurry,
        "n_no_face": n_no_face, "n_low_conf": n_low_conf,
        "max_det_score": round(max_det_score, 4),
        "max_crop_sharpness": round(max_crop_sharpness, 2),
    })

    logger.info(
        f"Enrollment : {n_valid}/{len(candidates)} embeddings valides "
        f"(blurry={n_blurry}, no_face={n_no_face}, low_conf={n_low_conf}, "
        f"augmentations_contribuant={n_aug_used})"
    )

    if not embeddings:
        logger.warning(
            "Enrollment échoué : aucun embedding valide après filtrage — "
            f"{format_enroll_diagnostics(diagnostics)} "
            f"(confidence≥{confidence_threshold}, netteté_crop≥{blur_threshold})"
        )
        return None

    # Multi-vecteurs : on retourne TOUS les embeddings valides (1 ligne chacun en
    # base). Chaque vecteur est déjà L2-normalisé (_l2_normalize ci-dessus).
    embeddings_out = [emb.astype(np.float32).tolist() for emb in embeddings]
    elapsed_ms = (time.perf_counter() - t0) * 1000

    logger.info(
        f"Enrollment multi-vecteurs : {n_valid} vecteur(s) 512-D conservé(s) "
        f"(aucun moyennage centroïde), durée={elapsed_ms:.1f}ms"
    )

    return embeddings_out, best_face_crop


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
    Pour l'enrollment, utiliser enroll_from_images() (galerie multi-vecteurs).
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

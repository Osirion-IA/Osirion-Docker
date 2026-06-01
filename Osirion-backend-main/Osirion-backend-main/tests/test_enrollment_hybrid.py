"""
Tests du système d'enrollment hybride : augmentation, centroid, qualité.

Lancement :
  pytest tests/test_enrollment_hybrid.py -v

Prérequis pour les tests avec visage réel :
  tests/assets/test_face.jpg  — photo nette, frontale, éclairée
"""
import numpy as np
import pytest


# ─────────────────────────────────────────────────────────────────────────────
# generate_augmented_images
# ─────────────────────────────────────────────────────────────────────────────

def test_augmentation_count():
    """generate_augmented_images doit retourner exactement 4 variantes."""
    import numpy as np
    from app.services.embeddings_service import generate_augmented_images

    rng = np.random.default_rng(0)
    img = rng.integers(50, 200, (480, 640, 3), dtype=np.uint8)
    variants = generate_augmented_images(img)

    assert len(variants) == 4, f"Attendu 4 variantes, obtenu {len(variants)}"


def test_augmentation_shape_preserved():
    """Chaque variante doit avoir la même shape que l'original."""
    import numpy as np
    from app.services.embeddings_service import generate_augmented_images

    rng = np.random.default_rng(1)
    img = rng.integers(0, 255, (480, 640, 3), dtype=np.uint8)
    variants = generate_augmented_images(img)

    for i, v in enumerate(variants):
        assert v.shape == img.shape, (
            f"Variant[{i}] shape={v.shape} != original shape={img.shape}"
        )


def test_augmentation_differs_from_source():
    """Chaque variante doit différer de l'image source (augmentation effective)."""
    import numpy as np
    from app.services.embeddings_service import generate_augmented_images

    rng = np.random.default_rng(42)
    img = rng.integers(30, 220, (480, 640, 3), dtype=np.uint8)
    variants = generate_augmented_images(img)

    for i, v in enumerate(variants):
        assert not np.array_equal(v, img), (
            f"Variant[{i}] identique à l'original — augmentation inactive ou incorrecte"
        )


# ─────────────────────────────────────────────────────────────────────────────
# compute_centroid_embedding
# ─────────────────────────────────────────────────────────────────────────────

def test_centroid_norm_unit():
    """Le centroid de N vecteurs L2-normalisés doit avoir norme ≈ 1.0."""
    from app.services.embeddings_service import compute_centroid_embedding

    rng = np.random.default_rng(0)
    embeddings = []
    for _ in range(5):
        v = rng.standard_normal(512).astype(np.float32)
        v /= np.linalg.norm(v)
        embeddings.append(v)

    centroid = compute_centroid_embedding(embeddings)
    norm = float(np.linalg.norm(centroid))

    assert abs(norm - 1.0) < 1e-5, (
        f"Norme centroid={norm:.8f} (attendu 1.0 ± 1e-5). "
        "La re-normalisation finale dans compute_centroid_embedding est-elle active ?"
    )


def test_centroid_dimension():
    """Le centroid doit être 512D."""
    from app.services.embeddings_service import compute_centroid_embedding

    rng = np.random.default_rng(1)
    embeddings = []
    for _ in range(3):
        v = rng.standard_normal(512).astype(np.float32)
        v /= np.linalg.norm(v)
        embeddings.append(v)

    centroid = compute_centroid_embedding(embeddings)
    assert centroid.shape == (512,), (
        f"Dimension centroid={centroid.shape} (attendu (512,))"
    )


def test_centroid_single_embedding_is_itself():
    """Centroid d'un seul embedding normalisé = cet embedding (à précision flottante près)."""
    from app.services.embeddings_service import compute_centroid_embedding

    rng = np.random.default_rng(2)
    v = rng.standard_normal(512).astype(np.float32)
    v /= np.linalg.norm(v)

    centroid = compute_centroid_embedding([v])
    np.testing.assert_allclose(centroid, v, atol=1e-6, err_msg="Centroid(1 emb) ≠ emb")


def test_centroid_identical_embeddings():
    """Centroid de N copies du même vecteur = ce vecteur."""
    from app.services.embeddings_service import compute_centroid_embedding

    rng = np.random.default_rng(3)
    v = rng.standard_normal(512).astype(np.float32)
    v /= np.linalg.norm(v)

    centroid = compute_centroid_embedding([v.copy() for _ in range(4)])
    np.testing.assert_allclose(centroid, v, atol=1e-6, err_msg="Centroid(4×emb) ≠ emb")


# ─────────────────────────────────────────────────────────────────────────────
# enroll_from_images — tests sans visage
# ─────────────────────────────────────────────────────────────────────────────

def test_enroll_blank_image_returns_none():
    """Une image vierge (sans visage) doit retourner None."""
    import numpy as np
    from app.services.embeddings_service import enroll_from_images

    blank = np.zeros((480, 640, 3), dtype=np.uint8)
    result = enroll_from_images([blank], confidence_threshold=0.5, blur_threshold=0.0)
    assert result is None, f"Image vierge ne doit pas retourner d'embedding : {result}"


def test_enroll_empty_list_returns_none():
    """Liste vide d'images doit retourner None sans lever d'exception."""
    from app.services.embeddings_service import enroll_from_images

    result = enroll_from_images([], confidence_threshold=0.5)
    assert result is None


# ─────────────────────────────────────────────────────────────────────────────
# enroll_from_images — tests avec visage réel (skip si image absente)
# ─────────────────────────────────────────────────────────────────────────────

def test_single_image_enrollment_augments(test_image_path):
    """
    CAS 1 : avec 1 image, le système doit utiliser l'augmentation et retourner
    un centroid valide (dim=512, norm≈1.0).
    """
    import cv2
    import numpy as np
    from app.services.embeddings_service import enroll_from_images, generate_augmented_images

    img = cv2.imread(test_image_path)

    # Vérification indirecte : 4 augmentations générées (structure)
    augmented = generate_augmented_images(img)
    assert len(augmented) == 4

    result = enroll_from_images([img], confidence_threshold=0.5, blur_threshold=0.0)
    if result is None:
        pytest.skip(
            "Image de test insuffisante pour enrollment (confidence < 0.5) — "
            "utiliser une photo frontale nette."
        )

    centroid, face_crop = result
    assert len(centroid) == 512, f"Dimension={len(centroid)} (attendu 512)"

    norm = np.linalg.norm(np.array(centroid, dtype=np.float32))
    assert abs(norm - 1.0) < 1e-4, f"Norm={norm:.6f} (attendu ≈ 1.0)"
    assert face_crop is not None and face_crop.size > 0


def test_multi_image_enrollment_no_augmentation(test_image_path):
    """
    CAS 2 : avec ≥ 2 images, pas d'augmentation — centroid sur les embeddings directs.
    Résultat : dim=512, norm≈1.0.
    """
    import cv2
    import numpy as np
    from app.services.embeddings_service import enroll_from_images

    img = cv2.imread(test_image_path)
    images = [img.copy() for _ in range(3)]

    result = enroll_from_images(images, confidence_threshold=0.5, blur_threshold=0.0)
    if result is None:
        pytest.skip("Image de test insuffisante pour enrollment.")

    centroid, face_crop = result
    assert len(centroid) == 512
    norm = np.linalg.norm(np.array(centroid, dtype=np.float32))
    assert abs(norm - 1.0) < 1e-4, f"Norm={norm:.6f} (attendu ≈ 1.0)"


def test_enroll_final_norm_is_unit(test_image_path):
    """
    Invariant critique : quelle que soit la stratégie (1 ou N images),
    l'embedding final doit avoir norme = 1.0 ± 1e-4.
    """
    import cv2
    import numpy as np
    from app.services.embeddings_service import enroll_from_images

    img = cv2.imread(test_image_path)

    for n in (1, 2, 4):
        result = enroll_from_images(
            [img.copy() for _ in range(n)],
            confidence_threshold=0.5,
            blur_threshold=0.0
        )
        if result is None:
            pytest.skip("Image de test insuffisante.")

        centroid, _ = result
        norm = np.linalg.norm(np.array(centroid, dtype=np.float32))
        assert abs(norm - 1.0) < 1e-4, (
            f"n={n} images → norm={norm:.6f} (attendu 1.0 ± 1e-4)"
        )


def test_enroll_max_5_images_cap(test_image_path):
    """enroll_from_images ne doit pas planter si on passe plus de 5 images (cap interne)."""
    import cv2
    from app.services.embeddings_service import enroll_from_images

    img = cv2.imread(test_image_path)
    images = [img.copy() for _ in range(8)]  # > _MAX_CENTROID_IMAGES=5

    # Ne doit pas lever d'exception (le cap est géré en interne)
    result = enroll_from_images(images, confidence_threshold=0.5, blur_threshold=0.0)
    # result peut être None si image insuffisante, mais pas d'exception

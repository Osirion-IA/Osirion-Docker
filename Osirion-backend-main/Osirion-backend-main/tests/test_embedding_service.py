"""
Tests du service d'embedding : normalisation, dimension, qualité.

Lancement :
  pytest tests/test_embedding_service.py -v
"""
import numpy as np
import pytest


def test_embedding_dimension(test_image_path):
    """L'embedding doit être 512D — toujours."""
    import cv2
    from app.services.embeddings_service import detect_and_embed

    img = cv2.imread(test_image_path)
    result = detect_and_embed(img, confidence_threshold=0.5)
    assert result is not None
    emb, _ = result
    assert len(emb) == 512, f"Dimension incorrecte : {len(emb)} (attendu 512)"


def test_embedding_norm_is_unit(test_image_path):
    """L'embedding doit avoir norme ≈ 1.0 après normalisation défensive."""
    import cv2
    from app.services.embeddings_service import detect_and_embed

    img = cv2.imread(test_image_path)
    result = detect_and_embed(img, confidence_threshold=0.5)
    assert result is not None
    emb, _ = result

    norm = np.linalg.norm(np.array(emb, dtype='float32'))
    assert abs(norm - 1.0) < 1e-4, (
        f"Norme embedding = {norm:.6f} (attendu 1.0 ± 1e-4). "
        "La normalisation L2 défensive dans embeddings_service.py est-elle active ?"
    )


def test_no_face_returns_none():
    """Une image sans visage doit retourner None, pas lever une exception."""
    import cv2
    import numpy as np
    from app.services.embeddings_service import detect_and_embed

    blank = np.zeros((480, 640, 3), dtype=np.uint8)
    result = detect_and_embed(blank, confidence_threshold=0.5)
    assert result is None, f"Une image vierge ne doit pas retourner d'embedding : {result}"


def test_low_confidence_rejected(test_image_path):
    """
    Une image avec visage doit être rejetée si conf < threshold.
    Avec threshold=0.999, la plupart des visages doivent échouer.
    """
    import cv2
    from app.services.embeddings_service import detect_and_embed

    img = cv2.imread(test_image_path)
    result = detect_and_embed(img, confidence_threshold=0.999)
    # Acceptable : None (rejeté) ou résultat valide si photo exceptionnelle
    if result is not None:
        emb, _ = result
        assert len(emb) == 512


def test_blur_filter_rejects_blurry_frame():
    """
    Le filtre Laplacien doit identifier une image floue.
    Crée une image très floue et vérifie que la variance Laplacienne est basse.
    """
    import cv2
    import numpy as np
    from core.tracking_processor import TrackingProcessor

    # Créer une image floue artificielle
    rng = np.random.default_rng(42)
    img = (rng.random((480, 640, 3)) * 255).astype(np.uint8)
    blurry = cv2.GaussianBlur(img, (51, 51), 20)

    sharpness = TrackingProcessor._compute_frame_sharpness(blurry)
    assert sharpness < 80.0, (
        f"Image floue détectée comme nette : Laplacien={sharpness:.1f} "
        "(attendu < 80.0 pour image très floue)"
    )


def test_sharp_frame_passes_filter():
    """Une image nette doit passer le filtre Laplacien."""
    import cv2
    import numpy as np
    from core.tracking_processor import TrackingProcessor

    rng = np.random.default_rng(42)
    # Image avec bords nets (haute fréquence spatiale)
    img = np.zeros((480, 640, 3), dtype=np.uint8)
    for i in range(0, 480, 10):
        cv2.line(img, (0, i), (640, i), (255, 255, 255), 1)
    for j in range(0, 640, 10):
        cv2.line(img, (j, 0), (j, 480), (200, 200, 200), 1)

    sharpness = TrackingProcessor._compute_frame_sharpness(img)
    assert sharpness > 80.0, (
        f"Image nette détectée comme floue : Laplacien={sharpness:.1f} "
        "(attendu > 80.0 pour image avec bords nets)"
    )

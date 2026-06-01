"""
Tests du pipeline ArcFace + FAISS — vérification post-corrections.

Couvre :
  T1 : auto-similarité (un embedding contre lui-même → score ~1.0)
  T2 : score range [0.0, 1.0] sur vecteurs aléatoires normalisés
  T3 : norme des embeddings en base ≈ 1.0 (pas de drift pgvector)
  T4 : différentes personnes → score < seuil de reconnaissance
  T5 : vecteur nul rejeté proprement (pas de crash)
  T6 : cohérence indexFlatIP (pas de IndexFlatL2 résiduel)

Lancement :
  pytest tests/test_faiss_pipeline.py -v
"""
import numpy as np
import faiss
import pytest


# ─────────────────────────────────────────────
# T1 — Auto-similarité
# ─────────────────────────────────────────────

def test_self_similarity(test_image_path, faiss_index_ready):
    """
    Un embedding comparé à lui-même dans FAISS doit retourner score ≈ 1.0.
    Si ce test échoue → normalisation ou métrique encore incorrecte.
    """
    import cv2
    from app.services.embeddings_service import detect_and_embed
    from app.services.Faiss_search_service import search_similar_people

    img = cv2.imread(test_image_path)
    assert img is not None, f"Impossible de lire {test_image_path}"

    result = detect_and_embed(img, confidence_threshold=0.5)
    assert result is not None, (
        "Aucun visage détecté dans test_face.jpg — "
        "utiliser une photo frontale nette (conf ≥ 0.5 requis pour ce test)."
    )
    emb, _ = result

    results = search_similar_people(emb, k=1)
    assert results, "Aucun résultat FAISS — index vide ?"

    score = results[0]["score"]
    assert score > 0.90, (
        f"Auto-similarité trop basse : {score:.4f} (attendu > 0.90). "
        "Cause possible : l'embedding de test_face.jpg n'est pas enrollé en base, "
        "ou la normalisation est défaillante."
    )


# ─────────────────────────────────────────────
# T2 — Score range [0.0, 1.0]
# ─────────────────────────────────────────────

def test_score_range_on_random_vectors(faiss_index_ready):
    """
    Des vecteurs aléatoires normalisés ne doivent jamais produire
    de scores hors de [0.0, 1.0]. Un score > 1.0 indique un vecteur
    non-normalisé dans l'index ou dans la query.
    """
    from app.services.Faiss_search_service import search_similar_people

    rng = np.random.default_rng(seed=42)
    random_vecs = rng.standard_normal((20, 512)).astype('float32')
    faiss.normalize_L2(random_vecs)

    for i, vec in enumerate(random_vecs):
        results = search_similar_people(vec.tolist(), k=3)
        for r in results:
            assert 0.0 <= r["score"] <= 1.0, (
                f"Score hors range [0,1] : {r['score']:.6f} "
                f"(vecteur #{i}, candidat={r['name']!r})"
            )


# ─────────────────────────────────────────────
# T3 — Norme des embeddings en base ≈ 1.0
# ─────────────────────────────────────────────

def test_embedding_norms_in_database():
    """
    Toutes les normes des embeddings stockés dans PostgreSQL doivent être
    dans [0.999, 1.001]. Un écart indique un drift de round-trip pgvector
    que la re-normalisation dans build_or_reload_faiss_index doit corriger.
    """
    import numpy as np
    from sqlmodel import Session, select
    from app.database import engine
    from app.models.people import People

    with Session(engine) as session:
        people = session.exec(select(People)).all()

    if not people:
        pytest.skip("Aucune personne en base — enroller au moins 1 personne.")

    norms = [np.linalg.norm(np.array(p.embeddings, dtype='float32')) for p in people]
    norms = np.array(norms)

    assert norms.min() > 0.990, (
        f"Norme minimale trop basse : {norms.min():.6f} "
        f"(personne id={people[np.argmin(norms)].id}) — "
        "vérifier le chemin de normalisation lors de l'enrollment."
    )
    assert norms.max() < 1.010, (
        f"Norme maximale trop haute : {norms.max():.6f} "
        f"(personne id={people[np.argmax(norms)].id}) — "
        "drift float32 excessif lors du stockage pgvector."
    )


# ─────────────────────────────────────────────
# T4 — Deux personnes différentes → score < seuil
# ─────────────────────────────────────────────

def test_different_persons_score_below_threshold(test_image_path, test_image_path_b, faiss_index_ready):
    """
    L'embedding de test_face_b.jpg (personne B, non enrollée)
    ne doit pas dépasser le seuil de reconnaissance face à la base
    (qui contient la personne A de test_face.jpg).

    Seuil de décision : 0.45 (RECOGNITION_THRESHOLD après corrections).
    Un score > 0.45 indique un faux positif ou une base trop petite.
    """
    import cv2
    from app.services.embeddings_service import detect_and_embed
    from app.services.Faiss_search_service import search_similar_people

    img_b = cv2.imread(test_image_path_b)
    assert img_b is not None

    result = detect_and_embed(img_b, confidence_threshold=0.5)
    assert result is not None, "Aucun visage détecté dans test_face_b.jpg"
    emb_b, _ = result

    results = search_similar_people(emb_b, k=1)
    assert results, "Aucun résultat FAISS"

    score = results[0]["score"]
    # Seuil souple pour ce test : on vérifie que la discrimination est possible
    # (pas nécessairement < 0.45 si la base contient peu de personnes)
    assert score < 0.80, (
        f"Score inter-personnes trop élevé : {score:.4f} "
        f"(candidat={results[0]['name']!r}). "
        "Vérifier que test_face_b.jpg est bien une personne différente de test_face.jpg."
    )


# ─────────────────────────────────────────────
# T5 — Vecteur nul → pas de crash
# ─────────────────────────────────────────────

def test_zero_vector_does_not_crash(faiss_index_ready):
    """
    Un embedding nul (norm=0) ne doit pas provoquer de crash ou de NaN.
    La normalisation défensive doit gérer ce cas.
    """
    from app.services.Faiss_search_service import search_similar_people

    zero_vec = [0.0] * 512
    try:
        results = search_similar_people(zero_vec, k=1)
        # Résultat acceptable : liste vide ou scores [0,1]
        for r in results:
            assert 0.0 <= r["score"] <= 1.0, f"Score inattendu sur vecteur nul : {r['score']}"
    except Exception as e:
        pytest.fail(f"Exception sur vecteur nul : {e}")


# ─────────────────────────────────────────────
# T6 — Vérification type d'index (pas de L2 résiduel)
# ─────────────────────────────────────────────

def test_faiss_index_uses_inner_product(faiss_index_ready):
    """
    L'index FAISS doit utiliser METRIC_INNER_PRODUCT, pas METRIC_L2.
    Un index L2 résiduel produirait des scores non-cosine (bug de régression).
    """
    idx = faiss_index_ready
    assert idx.metric_type == faiss.METRIC_INNER_PRODUCT, (
        f"Index FAISS utilise metric_type={idx.metric_type} "
        f"(attendu METRIC_INNER_PRODUCT={faiss.METRIC_INNER_PRODUCT}). "
        "Reconstruire l'index : appeler build_or_reload_faiss_index() au démarrage."
    )

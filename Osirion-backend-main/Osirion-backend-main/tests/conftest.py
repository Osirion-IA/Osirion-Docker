"""
Fixtures pytest partagées pour les tests du pipeline ArcFace + FAISS.

Prérequis :
  - Backend lancé avec au moins 1 personne enrollée (fixture 'enrolled_person')
  - Image test disponible : tests/assets/test_face.jpg (photo nette, frontale)
  - Variables d'environnement chargées depuis .env

Lancement :
  cd Osirion-backend-main
  pytest tests/ -v --tb=short
"""
import os
import sys
import pytest
import numpy as np
import faiss

# Ajouter le dossier racine du backend au sys.path pour que les imports app/* fonctionnent
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()


@pytest.fixture(scope="session")
def test_image_path():
    """Chemin vers l'image de test. Doit contenir un visage net et frontal."""
    path = os.path.join(os.path.dirname(__file__), "assets", "test_face.jpg")
    if not os.path.exists(path):
        pytest.skip(
            f"Image de test absente : {path}\n"
            "Créer tests/assets/test_face.jpg avec un visage net et frontal."
        )
    return path


@pytest.fixture(scope="session")
def test_image_path_b():
    """Deuxième visage — personne différente de test_face.jpg."""
    path = os.path.join(os.path.dirname(__file__), "assets", "test_face_b.jpg")
    if not os.path.exists(path):
        pytest.skip(
            f"Image test_face_b.jpg absente : {path}\n"
            "Créer tests/assets/test_face_b.jpg avec un visage différent de test_face.jpg."
        )
    return path


@pytest.fixture(scope="session")
def faiss_index_ready():
    """Vérifie que l'index FAISS est construit et contient au moins 1 vecteur."""
    from app.services.Faiss_search_service import build_or_reload_faiss_index, index
    if index is None or index.ntotal == 0:
        build_or_reload_faiss_index()
    from app.services.Faiss_search_service import index as idx
    if idx is None or idx.ntotal == 0:
        pytest.skip("Index FAISS vide — enroller au moins 1 personne avant de lancer les tests.")
    return idx

#!/usr/bin/env python3
"""
scripts/reenroll.py — Ré-enrôlement de masse après changement de backbone InsightFace.

Contexte
--------
Le passage de `buffalo_l` (ResNet-50) à `antelopev2` (ResNet-100) change l'ESPACE
d'embedding : les anciens vecteurs r50 stockés dans `person_embeddings` sont
incompatibles avec les requêtes r100 du Core (aucune correspondance). Ce script
régénère TOUS les embeddings à partir des images de référence, avec le pack courant
(`INSIGHTFACE_MODEL_PACK`, lu par app.services.embeddings_service à l'import).

Ce qu'il fait
-------------
1. se connecte à la base via la configuration SQLModel existante (app.database.engine) ;
2. parcourt toutes les personnes enrôlées (table `people`) ;
3. charge leur image de référence depuis le disque (`People.image_url`) ;
4. SUPPRIME leurs anciens vecteurs r50 (`person_embeddings`) ;
5. ré-exécute le pipeline d'extraction (pack antelopev2) → nouveaux vecteurs r100 ;
6. réécrit les nouveaux vecteurs dans `person_embeddings` ;
7. journalise une progression claire ("Successfully re-enrolled ...").

Sûreté
------
- TRANSACTION PAR PERSONNE : la suppression des anciens vecteurs et l'insertion des
  nouveaux sont commitées ensemble. En cas d'erreur → rollback (aucune perte).
- IMAGE INTROUVABLE / ILLISIBLE / SANS VISAGE → personne IGNORÉE et ses anciens
  vecteurs CONSERVÉS (on ne détruit jamais sans remplacement valide).
- N'écrit PAS dans l'index FAISS en mémoire de l'API (processus séparé) : il faut
  REDÉMARRER le backend après coup pour qu'il reconstruise l'index (cf. fin de log).

Limite connue
-------------
Seule l'image PRIMAIRE (`image_url`) est persistée à l'enrôlement ; les éventuelles
images supplémentaires d'un enrôlement multi-images ne sont pas conservées. Le
ré-enrôlement repart donc de cette image primaire (avec augmentation automatique →
plusieurs vecteurs r100), ce qui reste largement supérieur au centroïde r50 d'origine.

Usage (conteneurs démarrés)
---------------------------
    docker compose exec backend python scripts/reenroll.py
"""
import os
import sys
import logging
from pathlib import Path

import cv2
from sqlalchemy import delete
from sqlmodel import Session, select

# Exécution directe (python scripts/reenroll.py) : sys.path[0] vaut /app/scripts,
# pas /app → on ajoute la racine du projet (parent de scripts/) pour que le
# package `app` soit importable, quelle que soit la façon de lancer le script.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import engine
from app.models.people import People, PersonEmbedding
from app.services.embeddings_service import enroll_from_images

logging.basicConfig(
    level=logging.INFO,
    format="[reenroll] %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("reenroll")

# Seuil de confiance SCRFD pour la ré-extraction. Plus bas que l'enrôlement initial
# (0.85) : les images de référence sont DÉJÀ validées, on veut éviter d'en perdre à
# cause de petites différences de détection entre r50 et r100. Réglable par env.
REENROLL_CONFIDENCE = float(os.getenv("REENROLL_CONFIDENCE", "0.5"))
MODEL_PACK = os.getenv("INSIGHTFACE_MODEL_PACK", "antelopev2")


def _resolve_image_path(image_url: str | None) -> Path | None:
    """Localise l'image de référence sur le disque.

    `image_url` est typiquement un chemin relatif ("uploads/<hex>.jpg") par rapport
    à /app. On essaie le chemin tel quel, puis sous /app et le cwd, puis en repli par
    nom de fichier dans /app/uploads (volume nommé `uploads_data`)."""
    if not image_url:
        return None
    p = Path(image_url)
    candidates = [p]
    if not p.is_absolute():
        candidates.append(Path("/app") / image_url)
        candidates.append(Path.cwd() / image_url)
    candidates.append(Path("/app/uploads") / p.name)  # repli par basename
    for c in candidates:
        if c.is_file():
            return c
    return None


def reenroll_person(session: Session, person: People) -> bool:
    """Ré-enrôle UNE personne. Retourne True si remplacée, False si ignorée."""
    name = f"{person.first_name} {person.last_name}"

    img_path = _resolve_image_path(person.image_url)
    if img_path is None:
        logger.error(
            f"[SKIP] {name} (id={person.id}) — image introuvable : {person.image_url!r} "
            "(anciens vecteurs conservés)."
        )
        return False

    img = cv2.imread(str(img_path))
    if img is None:
        logger.error(
            f"[SKIP] {name} (id={person.id}) — image illisible : {img_path} "
            "(anciens vecteurs conservés)."
        )
        return False

    # Pipeline d'extraction multi-vecteurs avec le pack courant (antelopev2).
    result = enroll_from_images([img], confidence_threshold=REENROLL_CONFIDENCE)
    if result is None:
        logger.error(
            f"[SKIP] {name} (id={person.id}) — aucun visage exploitable "
            f"(confiance ≥ {REENROLL_CONFIDENCE}) (anciens vecteurs conservés)."
        )
        return False

    embeddings, _face_crop = result

    # Transaction : on remplace ATOMIQUEMENT les anciens vecteurs par les nouveaux.
    session.execute(
        delete(PersonEmbedding).where(PersonEmbedding.person_id == person.id)
    )
    for emb in embeddings:
        session.add(PersonEmbedding(person_id=person.id, embedding=emb))
    session.commit()

    logger.info(
        f"[OK] Successfully re-enrolled {name} (id={person.id}) — "
        f"{len(embeddings)} vecteur(s) r100 ({MODEL_PACK})."
    )
    return True


def main() -> int:
    logger.info(
        f"Ré-enrôlement de masse — pack='{MODEL_PACK}', confiance ≥ {REENROLL_CONFIDENCE}."
    )

    # Récupère les IDs sous une session courte ; chaque personne sera traitée dans
    # sa propre transaction ensuite.
    with Session(engine) as session:
        person_ids = list(session.exec(select(People.id)).all())

    total = len(person_ids)
    if total == 0:
        logger.info("Aucune personne en base — rien à faire.")
        return 0

    logger.info(f"{total} personne(s) à ré-enrôler.")

    ok = 0
    skipped = 0
    for pid in person_ids:
        with Session(engine) as session:
            person = session.get(People, pid)
            if person is None:
                logger.error(f"[SKIP] id={pid} — personne disparue entre-temps.")
                skipped += 1
                continue
            try:
                if reenroll_person(session, person):
                    ok += 1
                else:
                    skipped += 1
            except Exception:
                session.rollback()
                logger.exception(
                    f"[ERR] id={pid} — échec ré-enrôlement (rollback, anciens vecteurs conservés)."
                )
                skipped += 1

    logger.info(
        f"Terminé : {ok} ré-enrôlée(s), {skipped} ignorée(s)/échec(s) sur {total}."
    )
    logger.info(
        "IMPORTANT : redémarrez le backend pour reconstruire l'index FAISS "
        "(build_or_reload_faiss_index au démarrage), puis le core — par ex. : "
        "`docker compose restart backend core`."
    )
    # Code de sortie non nul si au moins une personne n'a pas pu être ré-enrôlée,
    # pour la visibilité en CI / scripts d'orchestration.
    return 0 if skipped == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

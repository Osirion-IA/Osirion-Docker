from fastapi import APIRouter, Depends, Request
from fastapi import Form, File, UploadFile
from app.services.bytesToImage_service import bytes_to_image
from app.services.embeddings_service import detect_and_embed, enroll_from_images
from app.services.saveImage_service import save_image_from_bytes, is_valid_image_format, MIME_TO_EXT
from app.services.Faiss_search_service import search_similar_people, add_person_to_index
from app.middleware.auth_middleware import can_add_people, require_viewer
from app.middleware.rate_limit import limiter
import numpy as np
from pydantic import BaseModel
from typing import List
import cv2
import logging
from pathlib import Path
from app.models.people import People
from app.database import engine
from sqlmodel import Session, select

router = APIRouter()
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers internes
# ─────────────────────────────────────────────────────────────────────────────

def _check_duplicate(embeddings: list) -> dict | None:
    """Retourne le doublon si cosine > 0.90, None sinon."""
    hits = search_similar_people(embeddings, k=1)
    if hits and hits[0]["score"] > 0.90:
        return hits[0]
    return None


async def _persist_person(
    first_name, last_name, phone, email, addresse,
    image_bytes, content_type, face_crop, embeddings
) -> dict:
    """Sauvegarde images + DB + FAISS. Lève une exception en cas d'échec."""
    original_path = await save_image_from_bytes(image_bytes, content_type, "uploads/")

    ext = MIME_TO_EXT.get(content_type, "jpg")
    success, buffer = cv2.imencode(f".{ext}", face_crop)
    if not success:
        Path(original_path).unlink(missing_ok=True)
        raise RuntimeError("Impossible de sauvegarder le visage recadré.")

    cropped_path = await save_image_from_bytes(buffer.tobytes(), content_type, "cropped/")

    new_person = People(
        first_name=first_name,
        last_name=last_name,
        phone=phone,
        email=email,
        addresse=addresse,
        image_url=original_path,
        embeddings=embeddings
    )
    with Session(engine) as session:
        session.add(new_person)
        session.commit()
        session.refresh(new_person)

    add_person_to_index(new_person.id, embeddings)
    return {"original_path": original_path, "cropped_path": cropped_path}


# ─────────────────────────────────────────────────────────────────────────────
# POST /upload/ — enrollment image unique (CAS 1 : augmentation automatique)
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/upload/")
@limiter.limit("10/minute")
async def add_people(
    request: Request,
    first_name: str = Form(...),
    last_name: str = Form(...),
    phone: str = Form(...),
    email: str = Form(...),
    addresse: str = Form(...),
    image_url: UploadFile = File(...),
    _current_user=Depends(can_add_people)
):
    """
    Enrollment avec une seule image.
    Le système génère automatiquement des augmentations légères (flip, rotation ±7°,
    luminosité) et calcule un centroid embedding pour plus de robustesse.
    """
    content_type = image_url.content_type or "image/jpeg"

    image_bytes = await image_url.read()
    await image_url.close()

    if not image_bytes:
        return {"error": "L'image est vide."}
    if not is_valid_image_format(image_url):
        return {"error": "Format d'image non supporté."}

    image = bytes_to_image(image_bytes)
    if image is None:
        return {"error": "Impossible de lire l'image."}

    # Enrollment hybride CAS 1 : 1 image → augmentation → centroid
    result = enroll_from_images([image], confidence_threshold=0.85)
    if result is None:
        return {
            "error": (
                "Aucun visage net détecté. "
                "Utilisez une photo frontale, bien éclairée (confiance SCRFD requise ≥ 0.85)."
            )
        }

    embeddings, face_crop = result

    dup = _check_duplicate(embeddings)
    if dup:
        logger.warning(
            f"Enrollment dupliqué refusé : candidat={dup['name']!r} score={dup['score']:.4f}"
        )
        return {
            "error": (
                f"Personne similaire déjà en base : {dup['name']} "
                f"(similarité={dup['score']:.2f}). "
                "Supprimez l'entrée existante avant de re-enroller."
            )
        }

    try:
        await _persist_person(
            first_name, last_name, phone, email, addresse,
            image_bytes, content_type, face_crop, embeddings
        )
        return {"message": "Personne ajoutée avec succès (centroid sur image augmentée)."}
    except Exception:
        logger.exception("Échec persist enrollment simple")
        return {"error": "Erreur lors de la sauvegarde — voir logs."}


# ─────────────────────────────────────────────────────────────────────────────
# POST /upload/multi/ — enrollment multi-images (CAS 2 : centroid direct)
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/upload/multi/")
@limiter.limit("5/minute")
async def add_people_multi(
    request: Request,
    first_name: str = Form(...),
    last_name: str = Form(...),
    phone: str = Form(...),
    email: str = Form(...),
    addresse: str = Form(...),
    images: List[UploadFile] = File(...),
    _current_user=Depends(can_add_people)
):
    """
    Enrollment avec plusieurs images (2–5).
    Aucune augmentation — centroid calculé directement sur les embeddings valides.
    Recommandé pour de meilleures photos : différents angles, éclairages variés.
    """
    if not images:
        return {"error": "Aucune image fournie."}
    if len(images) > 5:
        return {"error": "Maximum 5 images acceptées par enrollment."}

    frames: list = []
    primary_bytes: bytes | None = None
    primary_content_type = "image/jpeg"

    for upload in images:
        if not is_valid_image_format(upload):
            logger.debug(f"upload multi : format non supporté ({upload.filename}), skip")
            continue
        img_bytes = await upload.read()
        await upload.close()
        if not img_bytes:
            continue
        img = bytes_to_image(img_bytes)
        if img is None:
            continue
        frames.append(img)
        if primary_bytes is None:
            primary_bytes = img_bytes
            primary_content_type = upload.content_type or "image/jpeg"

    if not frames:
        return {"error": "Aucune image valide parmi les fichiers fournis."}

    if len(frames) == 1:
        logger.info(
            "upload/multi/ : une seule image valide reçue — "
            "bascule automatique sur enrollment avec augmentation (CAS 1)"
        )

    # Enrollment hybride : si frames==1 → augmentation auto, sinon centroid direct
    result = enroll_from_images(frames, confidence_threshold=0.85)
    if result is None:
        return {
            "error": (
                "Aucun visage net détecté dans les images fournies "
                "(confiance SCRFD requise ≥ 0.85, Laplacien ≥ 60)."
            )
        }

    embeddings, face_crop = result

    dup = _check_duplicate(embeddings)
    if dup:
        logger.warning(
            f"Enrollment multi dupliqué refusé : candidat={dup['name']!r} "
            f"score={dup['score']:.4f}"
        )
        return {
            "error": (
                f"Personne similaire déjà en base : {dup['name']} "
                f"(similarité={dup['score']:.2f}). "
                "Supprimez l'entrée existante avant de re-enroller."
            )
        }

    try:
        await _persist_person(
            first_name, last_name, phone, email, addresse,
            primary_bytes, primary_content_type, face_crop, embeddings
        )
        return {
            "message": (
                f"Personne ajoutée avec succès "
                f"(centroid sur {len(frames)} image(s))."
            )
        }
    except Exception:
        logger.exception("Échec persist enrollment multi-images")
        return {"error": "Erreur lors de la sauvegarde — voir logs."}


# ─────────────────────────────────────────────────────────────────────────────
# GET /list/
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/list/")
def list_people(_current_user=Depends(require_viewer)):
    with Session(engine) as session:
        people = session.execute(select(People)).scalars().all()
        return [
            {
                "id": person.id,
                "first_name": person.first_name,
                "last_name": person.last_name,
                "phone": person.phone,
                "email": person.email,
                "addresse": person.addresse,
                "image_url": person.image_url,
                "created_at": person.created_at,
            }
            for person in people
        ]


# ─────────────────────────────────────────────────────────────────────────────
# POST /search/
# ─────────────────────────────────────────────────────────────────────────────

class EmbeddingRequest(BaseModel):
    embedding: List[float]
    k: int = 3


@router.post("/search/")
@limiter.limit("600/minute")
def search_people(
    request: Request,
    req: EmbeddingRequest,
    _current_user=Depends(require_viewer)
):
    results = search_similar_people(req.embedding, req.k)
    if results:
        top = results[0]
        logger.info(
            f"[search] {len(results)} résultat(s) — top: name={top['name']!r} "
            f"cosine={top['score']:.4f} "
            f"[k={req.k}, caller={request.client.host}]"
        )
    else:
        logger.info(
            f"[search] Aucun résultat (index vide ou aucune correspondance) "
            f"[k={req.k}, caller={request.client.host}]"
        )
    return {"results": results}

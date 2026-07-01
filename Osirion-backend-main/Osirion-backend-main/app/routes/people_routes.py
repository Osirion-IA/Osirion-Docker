from fastapi import APIRouter, Depends, Request
from fastapi import Form, File, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from app.services.bytesToImage_service import bytes_to_image
from app.services.embeddings_service import detect_and_embed, enroll_from_images
from app.services.saveImage_service import save_image_from_bytes, is_valid_image_format, MIME_TO_EXT
from app.services.Faiss_search_service import search_similar_people, add_person_to_index
from app.middleware.auth_middleware import can_add_people, require_viewer, require_user
from app.schemas.people_schema import PersonBlacklistUpdate
from app.middleware.rate_limit import limiter
import numpy as np
from pydantic import BaseModel
from typing import List
import cv2
import logging
from pathlib import Path
from app.models.people import People, PersonEmbedding
from app.database import engine
from sqlmodel import Session, select
from sqlalchemy import func

router = APIRouter()
logger = logging.getLogger(__name__)


def _err(message: str, status: int = 400) -> JSONResponse:
    """Réponse d'erreur avec un VRAI code HTTP (pas 200) + corps {"error": ...}.
    Le frontend distingue ainsi un échec d'un succès (res.ok == false)."""
    return JSONResponse(status_code=status, content={"error": message})


# ─────────────────────────────────────────────────────────────────────────────
# Helpers internes
# ─────────────────────────────────────────────────────────────────────────────

def _check_duplicate(embeddings: list) -> dict | None:
    """Retourne le doublon si cosine > 0.90, None sinon.

    `embeddings` est désormais une LISTE de vecteurs (multi-vecteurs). On interroge
    avec chacun et on retient le meilleur score : si l'un des vecteurs candidats
    correspond fortement à une personne existante, c'est un doublon."""
    best: dict | None = None
    for emb in embeddings:
        hits = search_similar_people(emb, k=1)
        if hits and (best is None or hits[0]["score"] > best["score"]):
            best = hits[0]
    if best and best["score"] > 0.90:
        return best
    return None


async def _persist_person(
    first_name, last_name, phone, email, addresse,
    image_bytes, content_type, face_crop, embeddings
) -> dict:
    """Sauvegarde images + DB + FAISS. Lève une exception en cas d'échec.

    `embeddings` : liste de vecteurs 512-D (multi-vecteurs). On crée la personne
    puis une ligne `person_embeddings` par vecteur, et on ajoute chaque vecteur à
    l'index FAISS (mappé sur le person_id)."""
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
    )
    with Session(engine) as session:
        session.add(new_person)
        session.commit()
        session.refresh(new_person)
        person_id = new_person.id
        # Une ligne person_embeddings par vecteur (galerie multi-vecteurs).
        for emb in embeddings:
            session.add(PersonEmbedding(person_id=person_id, embedding=emb))
        session.commit()

    # Index FAISS : chaque vecteur pointe vers le MÊME person_id (max-cosine côté
    # recherche regroupe ensuite par personne).
    for emb in embeddings:
        add_person_to_index(person_id, emb)
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
        return _err("L'image est vide.", 400)
    if not is_valid_image_format(image_url):
        return _err("Format d'image non supporté.", 400)

    image = bytes_to_image(image_bytes)
    if image is None:
        return _err("Impossible de lire l'image.", 400)

    # Enrollment hybride CAS 1 : 1 image → augmentation → centroid
    result = enroll_from_images([image], confidence_threshold=0.85)
    if result is None:
        return _err(
            "Aucun visage net détecté. "
            "Utilisez une photo frontale, bien éclairée (confiance SCRFD requise ≥ 0.85).",
            422,
        )

    embeddings, face_crop = result

    dup = _check_duplicate(embeddings)
    if dup:
        logger.warning(
            f"Enrollment dupliqué refusé : candidat={dup['name']!r} score={dup['score']:.4f}"
        )
        return _err(
            f"Personne similaire déjà en base : {dup['name']} "
            f"(similarité={dup['score']:.2f}). "
            "Supprimez l'entrée existante avant de re-enroller.",
            409,
        )

    try:
        await _persist_person(
            first_name, last_name, phone, email, addresse,
            image_bytes, content_type, face_crop, embeddings
        )
        return {
            "message": (
                f"Personne ajoutée avec succès "
                f"({len(embeddings)} vecteur(s) sur image augmentée)."
            )
        }
    except IntegrityError:
        logger.warning("Enrollment refusé : téléphone ou email déjà utilisé.")
        return _err("Un compte avec ce téléphone ou cet email existe déjà.", 409)
    except Exception:
        logger.exception("Échec persist enrollment simple")
        return _err("Erreur lors de la sauvegarde — voir logs.", 500)


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
        return _err("Aucune image fournie.", 400)
    if len(images) > 5:
        return _err("Maximum 5 images acceptées par enrollment.", 400)

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
        return _err("Aucune image valide parmi les fichiers fournis.", 400)

    if len(frames) == 1:
        logger.info(
            "upload/multi/ : une seule image valide reçue — "
            "bascule automatique sur enrollment avec augmentation (CAS 1)"
        )

    # Enrollment hybride : si frames==1 → augmentation auto, sinon centroid direct
    result = enroll_from_images(frames, confidence_threshold=0.85)
    if result is None:
        return _err(
            "Aucun visage net détecté dans les images fournies "
            "(confiance SCRFD requise ≥ 0.85, Laplacien ≥ 60).",
            422,
        )

    embeddings, face_crop = result

    dup = _check_duplicate(embeddings)
    if dup:
        logger.warning(
            f"Enrollment multi dupliqué refusé : candidat={dup['name']!r} "
            f"score={dup['score']:.4f}"
        )
        return _err(
            f"Personne similaire déjà en base : {dup['name']} "
            f"(similarité={dup['score']:.2f}). "
            "Supprimez l'entrée existante avant de re-enroller.",
            409,
        )

    try:
        await _persist_person(
            first_name, last_name, phone, email, addresse,
            primary_bytes, primary_content_type, face_crop, embeddings
        )
        return {
            "message": (
                f"Personne ajoutée avec succès "
                f"({len(embeddings)} vecteur(s) sur {len(frames)} image(s))."
            )
        }
    except IntegrityError:
        logger.warning("Enrollment multi refusé : téléphone ou email déjà utilisé.")
        return _err("Un compte avec ce téléphone ou cet email existe déjà.", 409)
    except Exception:
        logger.exception("Échec persist enrollment multi-images")
        return _err("Erreur lors de la sauvegarde — voir logs.", 500)


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
                "is_blacklisted": bool(getattr(person, "is_blacklisted", False)),
                "blacklist_reason": getattr(person, "blacklist_reason", None),
                "created_at": person.created_at,
            }
            for person in people
        ]


# ─────────────────────────────────────────────────────────────────────────────
# POST /blacklist/{person_id} — (dé)marquer une personne surveillée  (USER/ADMIN)
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/blacklist/{person_id}")
def set_person_blacklist(
    person_id: int,
    payload: PersonBlacklistUpdate,
    _current_user=Depends(require_user),
):
    """Active/désactive le statut « liste de surveillance » d'une personne.

    Additif et idempotent : ne touche ni l'embedding ni les autres champs. Le
    Core lit ce statut via /people/search et déclenche l'alerte en conséquence."""
    with Session(engine) as session:
        person = session.get(People, person_id)
        if not person:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Personne non trouvée.")
        person.is_blacklisted = bool(payload.blacklisted)
        person.blacklist_reason = payload.reason if payload.blacklisted else None
        session.add(person)
        session.commit()
        session.refresh(person)
        logger.info(
            f"[people] id={person_id} blacklist={person.is_blacklisted} "
            f"reason={person.blacklist_reason!r}"
        )
        return {
            "id": person.id,
            "is_blacklisted": person.is_blacklisted,
            "blacklist_reason": person.blacklist_reason,
        }


# ─────────────────────────────────────────────────────────────────────────────
# GET /blacklist/ — liste légère des personnes surveillées (pour le Core)
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/blacklist/")
def list_blacklisted(_current_user=Depends(require_viewer)):
    """Renvoie les identifiants des personnes actuellement sur liste de surveillance.

    Endpoint volontairement minimal (ni embeddings ni images) : le Core l'interroge
    périodiquement pour appliquer un (dé)blacklist À CHAUD, sans attendre
    l'expiration de son cache de reconnaissance. Source de vérité = la DB."""
    with Session(engine) as session:
        rows = session.execute(
            select(People.id, People.first_name, People.last_name)
            .where(People.is_blacklisted == True)  # noqa: E712
        ).all()
        return {
            "ids": [r[0] for r in rows],
            "names": [f"{r[1]} {r[2]}" for r in rows],
            "count": len(rows),
        }


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


# ─────────────────────────────────────────────────────────────────────────────
# GET /embeddings/ et /embeddings/version
# Réplique LECTURE SEULE de la galerie pour le Core (recherche FAISS locale).
# PostgreSQL reste géré uniquement par le backend ; ces routes ne font qu'EXPOSER
# les embeddings + métadonnées pour que le Core en garde une copie en RAM.
# Additif : aucune route existante n'est modifiée.
# ─────────────────────────────────────────────────────────────────────────────

def _gallery_version(session: Session) -> str:
    """Empreinte légère de la galerie : change à chaque enrôlement ou toggle
    blacklist. Sert au Core de filet de sécurité (poll périodique) pour détecter
    qu'il doit recharger sa copie locale."""
    total = session.execute(select(func.count(People.id))).scalar() or 0
    blacklisted = session.execute(
        select(func.count(People.id)).where(People.is_blacklisted == True)  # noqa: E712
    ).scalar() or 0
    # Compte des vecteurs : change aussi quand on ajoute des embeddings à une
    # personne existante (multi-vecteurs), pas seulement à la création d'une personne.
    n_emb = session.execute(select(func.count(PersonEmbedding.id))).scalar() or 0
    last_created = session.execute(select(func.max(People.created_at))).scalar()
    return f"{total}:{n_emb}:{blacklisted}:{last_created.isoformat() if last_created else '0'}"


@router.get("/embeddings/version")
def embeddings_version(_current_user=Depends(require_viewer)):
    """Version courante de la galerie (sans transférer les embeddings)."""
    with Session(engine) as session:
        total = session.execute(select(func.count(People.id))).scalar() or 0
        return {"version": _gallery_version(session), "count": int(total)}


@router.get("/embeddings/")
def list_embeddings(_current_user=Depends(require_viewer)):
    """Galerie complète pour la construction de l'index FAISS local du Core.

    Multi-vecteurs : UNE entrée par vecteur (table person_embeddings), portant le
    `id` de la PERSONNE (donc potentiellement répété). Le Core regroupe ensuite par
    `id` en max-cosine (cf. core/face_index.py), à l'identique du backend. Appelé
    rarement (démarrage + réconciliation), jamais sur le chemin chaud."""
    with Session(engine) as session:
        rows = session.execute(
            select(
                People.id, People.first_name, People.last_name,
                People.is_blacklisted, People.blacklist_reason,
                People.phone, People.email, People.image_url,
                PersonEmbedding.embedding,
            ).join(PersonEmbedding, PersonEmbedding.person_id == People.id)
        ).all()
        items = [
            {
                "id": r[0],
                "name": f"{r[1]} {r[2]}",
                "is_blacklisted": bool(r[3]),
                "blacklist_reason": r[4],
                "phone": r[5],
                "email": r[6],
                "image_url": r[7],
                "embedding": np.asarray(r[8], dtype=float).tolist(),
            }
            for r in rows
        ]
        version = _gallery_version(session)
    return {"version": version, "count": len(items), "people": items}

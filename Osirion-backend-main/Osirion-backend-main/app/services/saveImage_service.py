import uuid
import shutil
from pathlib import Path
from fastapi import UploadFile, HTTPException
from typing import Set
import logging



ALLOWED_MIME_TYPES: Set[str] = {
    "image/jpeg", "image/jpg",
    "image/png",
    "image/webp",
    "image/gif",
    "image/bmp",
    "image/tiff",
    "image/avif",
    "image/heic",
    "image/jfif",
}

MIME_TO_EXT = {
    "image/jpeg": "jpg",
    "image/jpg":  "jpg",
    "image/png":  "png",
    "image/webp": "webp",
    "image/gif":  "gif",
    "image/bmp":  "bmp",
    "image/tiff": "tiff",
    "image/avif": "avif",
    "image/heic": "heic",
    "image/jfif": "jfif",
}


def is_valid_image_format(image: UploadFile) -> bool:
    """
    Vérifie si le content-type de l'image uploadée est autorisé.
    Retourne True si le format est valide, False sinon.
    """
    return image.content_type in ALLOWED_MIME_TYPES


def get_secure_extension(image: UploadFile) -> str:
    """
    Retourne l'extension sécurisée correspondant au content-type.
    À appeler uniquement après avoir validé le format avec is_valid_image_format().
    """
    return MIME_TO_EXT.get(image.content_type, "dat")  # fallback sécurisé


async def save_image_from_bytes(image_bytes: bytes, content_type: str, save_path: str) -> str:
    UPLOAD_DIR = Path(save_path)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    ext = MIME_TO_EXT.get(content_type or "image/jpeg", "jpg")
    unique_filename = f"{uuid.uuid4().hex}.{ext}"
    file_path = UPLOAD_DIR / unique_filename

    try:
        file_path.write_bytes(image_bytes)   # ← plus simple et plus sûr que open + write
        return str(file_path)
    except Exception as e:
        logging.error(f"ÉCHEC SAUVEGARDE → {file_path} | Erreur : {e!r}")  # ← cette ligne va tout te dire
        if file_path.exists():
            file_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"Impossible d'écrire le fichier : {e}") from e


async def save_uploaded_image(image: UploadFile, save_path:str) -> str:

    UPLOAD_DIR = Path(save_path)
    UPLOAD_DIR.mkdir(exist_ok=True)
    """
    Valide + enregistre l'image de façon sécurisée.
    Lève une HTTPException si le format n'est pas autorisé.
    Retourne le chemin relatif du fichier sauvegardé.
    """
    # 1. Vérification du format
    if not is_valid_image_format(image):
        raise HTTPException(
            status_code=400,
            detail=f"Format d'image non supporté. Autorisé : {', '.join(sorted(ALLOWED_MIME_TYPES))}"
        )

    # 2. Extension sécurisée
    ext = get_secure_extension(image)

    # 3. Nom unique + chemin
    unique_filename = f"{uuid.uuid4().hex}.{ext}"
    file_path = UPLOAD_DIR / unique_filename

    # 4. Sauvegarde en streaming
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(image.file, buffer)
    except Exception as e:
        if file_path.exists():
            file_path.unlink()
        raise HTTPException(
            status_code=500,
            detail="Erreur lors de la sauvegarde de l'image"
        ) from e
    finally:
        await image.close()

    return str(file_path)


# Tu peux toujours garder une fonction "tout-en-un" si tu veux garder l'API existante
async def save_image(image: UploadFile) -> str:
    """Compatibilité avec l'ancien nom de fonction"""
    return await save_uploaded_image(image)
from fastapi import APIRouter, HTTPException, Depends
from sqlmodel import Session, select
from typing import List

from app.models.cameras import Camera
from app.database import engine
from app.schemas.camera_schema import CameraCreate, CameraRead
from app.utils.security_utils import crypter, decrypter

# AJOUT : Import des middlewares de sécurité
from app.middleware.auth_middleware import (
    get_current_active_user,
    require_viewer,
    require_user,
    can_manage_cameras
)
from app.models.users import User

router = APIRouter()


def get_session():
    """Dépendance pour obtenir une session de base de données"""
    with Session(engine) as session:
        yield session


# ─────────────────────────────────────────────
# CREATE CAMERA (Protégé - USER ou ADMIN)
# ─────────────────────────────────────────────

@router.post("/add")
def add_camera(
    camera: CameraCreate,
    current_user: User = Depends(can_manage_cameras),  # ← Protection ajoutée
    session: Session = Depends(get_session)
):
    """
    Ajoute une nouvelle caméra.
    
    Permissions requises : USER ou ADMIN
    """
    cam_name = camera.cam_name
    rtsp_url = camera.rtsp_url
    location = camera.location
    is_active = camera.is_active

    if not cam_name or not rtsp_url:
        raise HTTPException(
            status_code=400, 
            detail="Le nom et l'URL de la caméra sont obligatoires."
        )

    new_camera = Camera(
        cam_name=cam_name,
        rtsp_url=crypter(rtsp_url), 
        location=location,
        is_active=is_active
    )

    session.add(new_camera)
    session.commit()
    session.refresh(new_camera)

    return {
        "message": "Caméra ajoutée avec succès !",
        "camera_id": new_camera.id,
        "added_by": current_user.email  # ← Traçabilité
    }


# ─────────────────────────────────────────────
# READ ALL CAMERAS (Protégé - Tous les rôles)
# ─────────────────────────────────────────────
@router.get("/", response_model=List[CameraRead])
def get_cameras(
    current_user: User = Depends(require_viewer),  # Protection ajoutée
    session: Session = Depends(get_session)
):
    """
    Liste toutes les caméras avec des informations explicites.
    
    Permissions requises : VIEWER, USER ou ADMIN
    """
    cameras = session.exec(select(Camera)).all()
    
    # Transformation pour rendre les données plus explicites
    cameras_list = [
        CameraRead(
            id=cam.id,
            cam_name=cam.cam_name,
            rtsp_url=decrypter(cam.rtsp_url),  # URL lisible si nécessaire
            location=cam.location,
            is_active=cam.is_active,
            created_at=cam.created_at
        )
        for cam in cameras
    ]
    
    return cameras_list


# ─────────────────────────────────────────────
# READ CAMERA BY ID (Protégé - Tous les rôles)
# ─────────────────────────────────────────────

@router.get("/{camera_id}", response_model=CameraRead)
def get_camera(
    camera_id: int,
    current_user: User = Depends(require_viewer),  # ← Protection ajoutée
    session: Session = Depends(get_session)
):
    """
    Récupère une caméra par son ID.
    
    Permissions requises : VIEWER, USER ou ADMIN
    """
    camera = session.get(Camera, camera_id)
    if not camera:
        raise HTTPException(status_code=404, detail="Caméra non trouvée")
    return camera


# ─────────────────────────────────────────────
# UPDATE CAMERA (Protégé - USER ou ADMIN)
# ─────────────────────────────────────────────

@router.put("/update/{camera_id}", response_model=CameraRead)
def update_camera(
    camera_id: int,
    camera_data: CameraCreate,
    current_user: User = Depends(can_manage_cameras),  # ← Protection ajoutée
    session: Session = Depends(get_session)
):
    """
    Met à jour une caméra.
    
    Permissions requises : USER ou ADMIN
    """
    camera = session.get(Camera, camera_id)
    if not camera:
        raise HTTPException(status_code=404, detail="Caméra non trouvée")

    camera.cam_name = camera_data.cam_name
    camera.rtsp_url = crypter(camera_data.rtsp_url)
    camera.location = camera_data.location
    camera.is_active = camera_data.is_active

    session.add(camera)
    session.commit()
    session.refresh(camera)

    return camera


# ─────────────────────────────────────────────
# DELETE CAMERA (Protégé - USER ou ADMIN)
# ─────────────────────────────────────────────

@router.delete("/delete/{camera_id}")
def delete_camera(
    camera_id: int,
    current_user: User = Depends(can_manage_cameras),  # ← Protection ajoutée
    session: Session = Depends(get_session)
):
    """
    Supprime une caméra.
    
    Permissions requises : USER ou ADMIN
    """
    camera = session.get(Camera, camera_id)
    if not camera:
        raise HTTPException(status_code=404, detail="Caméra non trouvée")
    
    session.delete(camera)
    session.commit()

    return {
        "message": f"Caméra {camera_id} supprimée avec succès !",
        "deleted_by": current_user.email  # ← Traçabilité
    }
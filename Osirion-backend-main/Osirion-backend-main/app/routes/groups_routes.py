from fastapi import APIRouter, HTTPException, Depends, status
from sqlmodel import Session, select
from sqlalchemy.orm import selectinload
from sqlalchemy.exc import IntegrityError
from typing import List

from app.models.camera_groups import CameraGroup
from app.models.cameras import Camera
from app.database import engine
from app.schemas.group_schema import (
    CameraGroupCreate,
    CameraGroupUpdate,
    CameraGroupRead,
)

from app.middleware.auth_middleware import require_viewer, can_manage_cameras
from app.models.users import User

router = APIRouter()


def get_session():
    """Dépendance pour obtenir une session de base de données."""
    with Session(engine) as session:
        yield session


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────
def _to_group_read(group: CameraGroup) -> CameraGroupRead:
    """Sérialise un groupe ORM (avec ses caméras chargées) en schéma de sortie."""
    camera_ids = [c.id for c in group.cameras]
    return CameraGroupRead(
        id=group.id,
        name=group.name,
        description=group.description,
        created_at=group.created_at,
        camera_ids=camera_ids,
        camera_count=len(camera_ids),
    )


def _get_group_or_404(session: Session, group_id: int) -> CameraGroup:
    group = session.get(CameraGroup, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Groupe de caméras non trouvé")
    return group


# ─────────────────────────────────────────────
# LIST GROUPS (VIEWER+)
# ─────────────────────────────────────────────
@router.get("/", response_model=List[CameraGroupRead])
def list_groups(
    current_user: User = Depends(require_viewer),
    session: Session = Depends(get_session),
):
    """Liste tous les groupes de caméras avec leurs membres."""
    groups = session.exec(
        select(CameraGroup).options(selectinload(CameraGroup.cameras))
    ).all()
    return [_to_group_read(g) for g in groups]


# ─────────────────────────────────────────────
# CREATE GROUP (USER/ADMIN)
# ─────────────────────────────────────────────
@router.post("/", response_model=CameraGroupRead, status_code=status.HTTP_201_CREATED)
def create_group(
    payload: CameraGroupCreate,
    current_user: User = Depends(can_manage_cameras),
    session: Session = Depends(get_session),
):
    """Crée un groupe de caméras. Le nom doit être unique."""
    if not payload.name or not payload.name.strip():
        raise HTTPException(status_code=400, detail="Le nom du groupe est obligatoire.")

    group = CameraGroup(
        name=payload.name.strip(),
        description=payload.description,
    )
    session.add(group)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status_code=409,
            detail=f"Un groupe nommé « {payload.name.strip()} » existe déjà.",
        )
    session.refresh(group)
    return _to_group_read(group)


# ─────────────────────────────────────────────
# READ GROUP BY ID (VIEWER+)
# ─────────────────────────────────────────────
@router.get("/{group_id}", response_model=CameraGroupRead)
def get_group(
    group_id: int,
    current_user: User = Depends(require_viewer),
    session: Session = Depends(get_session),
):
    """Récupère un groupe par son ID."""
    group = _get_group_or_404(session, group_id)
    return _to_group_read(group)


# ─────────────────────────────────────────────
# UPDATE GROUP (USER/ADMIN)
# ─────────────────────────────────────────────
@router.put("/{group_id}", response_model=CameraGroupRead)
def update_group(
    group_id: int,
    payload: CameraGroupUpdate,
    current_user: User = Depends(can_manage_cameras),
    session: Session = Depends(get_session),
):
    """Met à jour un groupe (mise à jour partielle : seuls les champs fournis)."""
    group = _get_group_or_404(session, group_id)

    data = payload.model_dump(exclude_unset=True)
    if "name" in data and data["name"] is not None:
        name = data["name"].strip()
        if not name:
            raise HTTPException(status_code=400, detail="Le nom du groupe ne peut pas être vide.")
        group.name = name
    if "description" in data:
        group.description = data["description"]

    session.add(group)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(status_code=409, detail="Ce nom de groupe est déjà utilisé.")
    session.refresh(group)
    return _to_group_read(group)


# ─────────────────────────────────────────────
# DELETE GROUP (USER/ADMIN)
# ─────────────────────────────────────────────
@router.delete("/{group_id}")
def delete_group(
    group_id: int,
    current_user: User = Depends(can_manage_cameras),
    session: Session = Depends(get_session),
):
    """Supprime un groupe.

    Les liens caméra↔groupe sont supprimés en CASCADE (FK ON DELETE CASCADE) :
    les CAMÉRAS elles-mêmes ne sont PAS supprimées, seule leur appartenance à ce
    groupe disparaît. Leur config effective est recalculée au prochain GET.
    """
    group = _get_group_or_404(session, group_id)
    session.delete(group)
    session.commit()
    return {
        "message": f"Groupe {group_id} supprimé avec succès.",
        "deleted_by": current_user.email,
    }


# ─────────────────────────────────────────────
# ADD CAMERA TO GROUP (USER/ADMIN)
# ─────────────────────────────────────────────
@router.post("/{group_id}/cameras/{camera_id}", response_model=CameraGroupRead)
def add_camera_to_group(
    group_id: int,
    camera_id: int,
    current_user: User = Depends(can_manage_cameras),
    session: Session = Depends(get_session),
):
    """Ajoute une caméra à un groupe (idempotent)."""
    group = _get_group_or_404(session, group_id)
    camera = session.get(Camera, camera_id)
    if not camera:
        raise HTTPException(status_code=404, detail="Caméra non trouvée")

    if camera.id not in {c.id for c in group.cameras}:
        group.cameras.append(camera)
        session.add(group)
        session.commit()
        session.refresh(group)

    return _to_group_read(group)


# ─────────────────────────────────────────────
# REMOVE CAMERA FROM GROUP (USER/ADMIN)
# ─────────────────────────────────────────────
@router.delete("/{group_id}/cameras/{camera_id}", response_model=CameraGroupRead)
def remove_camera_from_group(
    group_id: int,
    camera_id: int,
    current_user: User = Depends(can_manage_cameras),
    session: Session = Depends(get_session),
):
    """Retire une caméra d'un groupe (idempotent : 404 seulement si le groupe
    ou la caméra n'existe pas, pas si le lien est déjà absent)."""
    group = _get_group_or_404(session, group_id)
    camera = session.get(Camera, camera_id)
    if not camera:
        raise HTTPException(status_code=404, detail="Caméra non trouvée")

    member = next((c for c in group.cameras if c.id == camera_id), None)
    if member is not None:
        group.cameras.remove(member)
        session.add(group)
        session.commit()
        session.refresh(group)

    return _to_group_read(group)

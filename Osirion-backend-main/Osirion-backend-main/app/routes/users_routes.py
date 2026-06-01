from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select
from typing import List
from datetime import datetime

from app.database import engine
from app.models.users import User, UserRole
from app.schemas.auth_schema import UserCreate, UserRead, UserUpdate
from app.middleware.auth_middleware import (
    get_current_active_user,
    require_admin,
    can_modify_users,
    can_delete_users
)
from app.utils.auth_utils import hash_password

router = APIRouter()


def get_session():
    """Dépendance pour obtenir une session de base de données"""
    with Session(engine) as session:
        yield session


# ─────────────────────────────────────────────
# LISTE DES UTILISATEURS (Admin uniquement)
# ─────────────────────────────────────────────

@router.get("/", response_model=List[UserRead])
def get_all_users(
    current_user: User = Depends(require_admin),
    session: Session = Depends(get_session)
):
    """
    Liste tous les utilisateurs.
    
    Permissions requises : ADMIN
    """
    users = session.exec(select(User)).all()
    return users


# ─────────────────────────────────────────────
# RÉCUPÉRER UN UTILISATEUR PAR ID (Admin)
# ─────────────────────────────────────────────

@router.get("/{user_id}", response_model=UserRead)
def get_user_by_id(
    user_id: int,
    current_user: User = Depends(require_admin),
    session: Session = Depends(get_session)
):
    """
    Récupère un utilisateur par son ID.
    
    Permissions requises : ADMIN
    """
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Utilisateur non trouvé"
        )
    return user


# ─────────────────────────────────────────────
# CRÉER UN UTILISATEUR (Admin uniquement)
# ─────────────────────────────────────────────

@router.post("/create", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def create_user(
    user_data: UserCreate,
    current_user: User = Depends(require_admin),
    session: Session = Depends(get_session)
):
    """
    Crée un nouvel utilisateur.
    
    Permissions requises : ADMIN
    """
    # Vérifier si l'email existe déjà
    existing_user = session.exec(
        select(User).where(User.email == user_data.email)
    ).first()
    
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Un utilisateur avec cet email existe déjà"
        )
    
    # Créer le nouvel utilisateur
    new_user = User(
        fullName=user_data.fullName,
        email=user_data.email,
        usr_password=hash_password(user_data.password),
        role=user_data.role.value,
        is_active=True,
        is_verified=True  # Les utilisateurs créés par admin sont pré-vérifiés
    )
    
    session.add(new_user)
    session.commit()
    session.refresh(new_user)
    
    return new_user


# ─────────────────────────────────────────────
# METTRE À JOUR UN UTILISATEUR (Admin)
# ─────────────────────────────────────────────

@router.put("/update/{user_id}", response_model=UserRead)
def update_user(
    user_id: int,
    user_data: UserUpdate,
    current_user: User = Depends(can_modify_users),
    session: Session = Depends(get_session)
):
    """
    Met à jour un utilisateur.
    
    Permissions requises : ADMIN
    """
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Utilisateur non trouvé"
        )
    
    # Empêcher un admin de se désactiver lui-même
    if user.id == current_user.id and user_data.is_active is False:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vous ne pouvez pas désactiver votre propre compte"
        )
    
    # Mettre à jour les champs fournis
    update_data = user_data.dict(exclude_unset=True)
    for key, value in update_data.items():
        if key == "role" and value:
            setattr(user, key, value.value)
        else:
            setattr(user, key, value)
    
    user.updated_at = datetime.utcnow()
    
    session.add(user)
    session.commit()
    session.refresh(user)
    
    return user


# ─────────────────────────────────────────────
# SUPPRIMER UN UTILISATEUR (Admin)
# ─────────────────────────────────────────────

@router.delete("/delete/{user_id}")
def delete_user(
    user_id: int,
    current_user: User = Depends(can_delete_users),
    session: Session = Depends(get_session)
):
    """
    Supprime un utilisateur.
    
    Permissions requises : ADMIN
    """
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Utilisateur non trouvé"
        )
    
    # Empêcher un admin de se supprimer lui-même
    if user.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vous ne pouvez pas supprimer votre propre compte"
        )
    
    session.delete(user)
    session.commit()
    
    return {
        "message": f"Utilisateur {user.email} supprimé avec succès",
        "deleted_by": current_user.email
    }


# ─────────────────────────────────────────────
# CHANGER LE RÔLE D'UN UTILISATEUR (Admin)
# ─────────────────────────────────────────────

@router.patch("/{user_id}/role")
def change_user_role(
    user_id: int,
    new_role: UserRole,
    current_user: User = Depends(require_admin),
    session: Session = Depends(get_session)
):
    """
    Change le rôle d'un utilisateur.
    
    Permissions requises : ADMIN
    """
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Utilisateur non trouvé"
        )
    
    # Empêcher de modifier son propre rôle
    if user.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vous ne pouvez pas modifier votre propre rôle"
        )
    
    old_role = user.role
    user.role = new_role.value
    user.updated_at = datetime.utcnow()
    
    session.add(user)
    session.commit()
    
    return {
        "message": f"Rôle de {user.email} changé de {old_role} à {new_role.value}",
        "changed_by": current_user.email
    }


# ─────────────────────────────────────────────
# ACTIVER/DÉSACTIVER UN UTILISATEUR (Admin)
# ─────────────────────────────────────────────

@router.patch("/{user_id}/toggle-active")
def toggle_user_active(
    user_id: int,
    current_user: User = Depends(require_admin),
    session: Session = Depends(get_session)
):
    """
    Active ou désactive un utilisateur.
    
    Permissions requises : ADMIN
    """
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Utilisateur non trouvé"
        )
    
    # Empêcher de se désactiver soi-même
    if user.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vous ne pouvez pas désactiver votre propre compte"
        )
    
    user.is_active = not user.is_active
    user.updated_at = datetime.utcnow()
    
    session.add(user)
    session.commit()
    
    status_text = "activé" if user.is_active else "désactivé"
    return {
        "message": f"Compte de {user.email} {status_text}",
        "is_active": user.is_active,
        "changed_by": current_user.email
    }
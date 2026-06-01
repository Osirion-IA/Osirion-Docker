from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlmodel import Session, select
from typing import Optional
from app.database import engine
from app.models.users import User, UserRole
from app.utils.auth_utils import decode_token, verify_token_type, is_account_locked
from datetime import datetime

# Configuration du schéma de sécurité Bearer
security = HTTPBearer()


def get_session():
    """Dépendance pour obtenir une session de base de données"""
    with Session(engine) as session:
        yield session


# ─────────────────────────────────────────────
# DÉPENDANCE : RÉCUPÉRATION DE L'UTILISATEUR COURANT
# ─────────────────────────────────────────────

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    session: Session = Depends(get_session)
) -> User:
    """
    Récupère l'utilisateur courant à partir du token JWT.
    
    Args:
        credentials: Credentials Bearer contenant le token
        session: Session de base de données
        
    Returns:
        Instance de l'utilisateur authentifié
        
    Raises:
        HTTPException: Si le token est invalide ou l'utilisateur n'existe pas
    """
    token = credentials.credentials
    
    # Décoder le token
    payload = decode_token(token)
    
    # Vérifier que c'est un access token
    verify_token_type(payload, "access")
    
    # Récupérer l'ID utilisateur
    user_id: int = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalide : utilisateur non trouvé",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Récupérer l'utilisateur en base
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Utilisateur non trouvé",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Vérifier que le compte est actif
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Compte désactivé"
        )
    
    # Vérifier que le compte n'est pas verrouillé
    if is_account_locked(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Compte verrouillé jusqu'à {user.locked_until.isoformat()}"
        )
    
    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """
    Récupère l'utilisateur courant et vérifie qu'il est actif.
    
    Args:
        current_user: Utilisateur authentifié
        
    Returns:
        Instance de l'utilisateur actif
        
    Raises:
        HTTPException: Si le compte n'est pas actif
    """
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Compte inactif"
        )
    return current_user


# ─────────────────────────────────────────────
# DÉPENDANCES : CONTRÔLE D'ACCÈS PAR RÔLE
# ─────────────────────────────────────────────

class RoleChecker:
    """Classe pour vérifier les rôles utilisateur"""
    
    def __init__(self, allowed_roles: list[UserRole]):
        self.allowed_roles = allowed_roles
    
    def __call__(self, user: User = Depends(get_current_active_user)) -> User:
        if user.role not in [role.value for role in self.allowed_roles]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Accès refusé. Rôles autorisés : {', '.join([r.value for r in self.allowed_roles])}"
            )
        return user


# Dépendances pré-configurées pour chaque rôle
require_admin = RoleChecker([UserRole.ADMIN])
require_user = RoleChecker([UserRole.ADMIN, UserRole.USER])
require_viewer = RoleChecker([UserRole.ADMIN, UserRole.USER, UserRole.VIEWER])


# ─────────────────────────────────────────────
# DÉPENDANCES : PERMISSIONS SPÉCIFIQUES
# ─────────────────────────────────────────────

async def can_modify_users(
    current_user: User = Depends(get_current_active_user)
) -> User:
    """Vérifie si l'utilisateur peut modifier d'autres utilisateurs"""
    if current_user.role != UserRole.ADMIN.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seuls les administrateurs peuvent modifier les utilisateurs"
        )
    return current_user


async def can_delete_users(
    current_user: User = Depends(get_current_active_user)
) -> User:
    """Vérifie si l'utilisateur peut supprimer d'autres utilisateurs"""
    if current_user.role != UserRole.ADMIN.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seuls les administrateurs peuvent supprimer les utilisateurs"
        )
    return current_user


async def can_manage_cameras(
    current_user: User = Depends(get_current_active_user)
) -> User:
    """Vérifie si l'utilisateur peut gérer les caméras"""
    if current_user.role not in [UserRole.ADMIN.value, UserRole.USER.value]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission insuffisante pour gérer les caméras"
        )
    return current_user


async def can_add_people(
    current_user: User = Depends(get_current_active_user)
) -> User:
    """Vérifie si l'utilisateur peut ajouter des personnes"""
    if current_user.role not in [UserRole.ADMIN.value, UserRole.USER.value]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission insuffisante pour ajouter des personnes"
        )
    return current_user
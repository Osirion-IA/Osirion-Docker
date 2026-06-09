from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlmodel import Session, select
from datetime import datetime, timedelta
from typing import Optional
import secrets

from app.database import engine
from app.models.users import User, UserRole, RefreshToken
from app.schemas.auth_schema import (
    UserRegister, UserLogin, TokenResponse, TokenRefresh,
    UserProfile, PasswordChange, PasswordResetRequest, PasswordReset
)
from app.utils.auth_utils import (
    hash_password, verify_password, create_access_token, create_refresh_token,
    decode_token, verify_token_type, is_account_locked, should_lock_account,
    calculate_lock_duration, create_reset_token
)
from app.middleware.auth_middleware import get_current_active_user
from app.middleware.rate_limit import limiter, RATE_LIMITS
from app.config import settings
from app.services.audit_service import record_audit
from app.services.notification_service import send_email

router = APIRouter()


def get_session():
    """Dépendance pour obtenir une session de base de données"""
    with Session(engine) as session:
        yield session


# ─────────────────────────────────────────────
# INSCRIPTION
# ─────────────────────────────────────────────

@router.post("/register", response_model=UserProfile, status_code=status.HTTP_201_CREATED)
@limiter.limit(RATE_LIMITS["register"])
async def register(
    request: Request,
    user_data: UserRegister,
    session: Session = Depends(get_session)
):
    """
    Inscription d'un nouvel utilisateur.
    
    - Par défaut, le rôle est 'viewer'
    - Le mot de passe est hashé avant stockage
    - Vérifie que l'email n'existe pas déjà
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
        role=UserRole.VIEWER.value,  # Rôle par défaut
        is_active=True,
        is_verified=False  # Nécessite une vérification email (à implémenter)
    )
    
    session.add(new_user)
    session.commit()
    session.refresh(new_user)
    
    return new_user


# ─────────────────────────────────────────────
# CONNEXION
# ─────────────────────────────────────────────

@router.post("/login", response_model=TokenResponse)
@limiter.limit(RATE_LIMITS["login"])
async def login(
    request: Request,
    credentials: UserLogin,
    session: Session = Depends(get_session)
):
    """
    Connexion d'un utilisateur.
    
    - Vérifie les credentials
    - Génère un access token et un refresh token
    - Gère le verrouillage du compte après échecs répétés
    """
    # Récupérer l'utilisateur
    user = session.exec(
        select(User).where(User.email == credentials.email)
    ).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email ou mot de passe incorrect"
        )
    
    # Vérifier si le compte est verrouillé
    if is_account_locked(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Compte verrouillé jusqu'à {user.locked_until.isoformat()}"
        )
    
    # Vérifier le mot de passe
    if not verify_password(credentials.password, user.usr_password):
        # Incrémenter les tentatives échouées
        user.failed_login_attempts += 1
        record_audit(
            "login.failure", user_id=user.id, user_email=user.email,
            ip_address=(request.client.host if request.client else None),
            detail=f"tentative #{user.failed_login_attempts}",
        )
        
        # Verrouiller le compte si nécessaire
        if should_lock_account(user.failed_login_attempts):
            lock_duration = calculate_lock_duration(user.failed_login_attempts)
            user.locked_until = datetime.utcnow() + lock_duration
            session.add(user)
            session.commit()
            
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Trop de tentatives échouées. Compte verrouillé pour {lock_duration.seconds // 60} minutes"
            )
        
        session.add(user)
        session.commit()
        
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email ou mot de passe incorrect"
        )
    
    # Vérifier que le compte est actif
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Compte désactivé"
        )
    
    # Réinitialiser les tentatives échouées et mettre à jour last_login
    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login = datetime.utcnow()
    session.add(user)
    record_audit(
        "login.success", user_id=user.id, user_email=user.email,
        ip_address=(request.client.host if request.client else None),
    )

    # Créer les tokens
    token_data = {
        "sub": str(user.id),
        "email": user.email,
        "role": user.role
    }
    
    access_token = create_access_token(token_data)
    refresh_token_str = create_refresh_token({"sub": str(user.id),})
    
    # Sauvegarder le refresh token en base
    refresh_token = RefreshToken(
        user_id=user.id,
        token=refresh_token_str,
        expires_at=datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        device_info=request.headers.get("User-Agent", "Unknown"),
        ip_address=request.client.host if request.client else None
    )
    session.add(refresh_token)
    session.commit()
    
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token_str,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )


# ─────────────────────────────────────────────
# RAFRAÎCHISSEMENT DU TOKEN
# ─────────────────────────────────────────────

@router.post("/refresh", response_model=TokenResponse)
@limiter.limit(RATE_LIMITS["token_refresh"])
async def refresh_token(
    request: Request,
    token_data: TokenRefresh,
    session: Session = Depends(get_session)
):
    """
    Rafraîchit l'access token à l'aide du refresh token.
    
    - Vérifie la validité du refresh token
    - Génère un nouvel access token
    - Optionnellement, génère un nouveau refresh token (rotation)
    """
    # Décoder le refresh token
    payload = decode_token(token_data.refresh_token)
    verify_token_type(payload, "refresh")
    
    user_id = payload.get("sub")
    jti = payload.get("jti")
    
    # Vérifier que le token existe en base et n'est pas révoqué
    db_token = session.exec(
        select(RefreshToken).where(
            RefreshToken.token == token_data.refresh_token,
            RefreshToken.user_id == user_id,
            RefreshToken.is_revoked == False
        )
    ).first()
    
    if not db_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token invalide ou révoqué"
        )
    
    # Vérifier l'expiration
    if datetime.utcnow() > db_token.expires_at:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token expiré"
        )
    
    # Récupérer l'utilisateur
    user = session.get(User, user_id)
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Utilisateur non trouvé ou inactif"
        )
    
    # Créer un nouvel access token
    token_data_payload = {
        "sub": user.id,
        "email": user.email,
        "role": user.role
    }
    new_access_token = create_access_token(token_data_payload)
    
    # Rotation du refresh token (optionnel mais recommandé)
    # Révoquer l'ancien et créer un nouveau
    db_token.is_revoked = True
    session.add(db_token)
    
    new_refresh_token_str = create_refresh_token({"sub": str(user.id)})
    new_refresh_token = RefreshToken(
        user_id=user.id,
        token=new_refresh_token_str,
        expires_at=datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        device_info=request.headers.get("User-Agent", "Unknown"),
        ip_address=request.client.host if request.client else None
    )
    session.add(new_refresh_token)
    session.commit()
    
    return TokenResponse(
        access_token=new_access_token,
        refresh_token=new_refresh_token_str,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )


# ─────────────────────────────────────────────
# DÉCONNEXION
# ─────────────────────────────────────────────

@router.post("/logout")
async def logout(
    token_data: TokenRefresh,
    current_user: User = Depends(get_current_active_user),
    session: Session = Depends(get_session)
):
    """
    Déconnexion d'un utilisateur.
    
    - Révoque le refresh token fourni
    """
    # Révoquer le refresh token
    db_token = session.exec(
        select(RefreshToken).where(
            RefreshToken.token == token_data.refresh_token,
            RefreshToken.user_id == current_user.id
        )
    ).first()
    
    if db_token:
        db_token.is_revoked = True
        session.add(db_token)
        session.commit()
    
    return {"message": "Déconnexion réussie"}


# ─────────────────────────────────────────────
# PROFIL UTILISATEUR
# ─────────────────────────────────────────────

@router.get("/me", response_model=UserProfile)
async def get_my_profile(
    current_user: User = Depends(get_current_active_user)
):
    """Récupère le profil de l'utilisateur connecté"""
    return current_user


# ─────────────────────────────────────────────
# CHANGEMENT DE MOT DE PASSE
# ─────────────────────────────────────────────

@router.post("/change-password")
async def change_password(
    password_data: PasswordChange,
    current_user: User = Depends(get_current_active_user),
    session: Session = Depends(get_session)
):
    """
    Change le mot de passe de l'utilisateur connecté.
    
    - Vérifie l'ancien mot de passe
    - Hash et enregistre le nouveau
    """
    # Vérifier l'ancien mot de passe
    if not verify_password(password_data.old_password, current_user.usr_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ancien mot de passe incorrect"
        )
    
    # Mettre à jour le mot de passe
    current_user.usr_password = hash_password(password_data.new_password)
    current_user.updated_at = datetime.utcnow()
    
    session.add(current_user)
    session.commit()
    
    return {"message": "Mot de passe changé avec succès"}


# ─────────────────────────────────────────────
# RÉINITIALISATION DE MOT DE PASSE (Optionnel)
# ─────────────────────────────────────────────

@router.post("/password-reset-request")
@limiter.limit(RATE_LIMITS["password_reset"])
async def request_password_reset(
    request: Request,
    reset_request: PasswordResetRequest,
    session: Session = Depends(get_session)
):
    """
    Demande de réinitialisation de mot de passe.
    
    Note : Cette route nécessite un service d'email pour envoyer le lien.
    Pour l'instant, elle retourne juste un message de succès.
    """
    user = session.exec(
        select(User).where(User.email == reset_request.email)
    ).first()

    # Ne pas révéler si l'email existe ou non (sécurité). Si SMTP est configuré,
    # un token court (30 min) est envoyé ; sinon la demande est simplement tracée.
    if user:
        token = create_reset_token(user.id, minutes=30)
        subject = "[Osirion] Réinitialisation de votre mot de passe"
        body = (
            "Vous avez demandé la réinitialisation de votre mot de passe Osirion.\n\n"
            "Jeton (valide 30 minutes) à fournir à POST /auth/password-reset-confirm "
            "avec votre nouveau mot de passe :\n\n"
            f"{token}\n\n"
            "Si vous n'êtes pas à l'origine de cette demande, ignorez cet email."
        )
        ok, msg = send_email(subject, body, to=user.email)
        record_audit(
            "password.reset_request", user_id=user.id, user_email=user.email,
            ip_address=(request.client.host if request.client else None),
            detail=("email envoyé" if ok else f"email non envoyé: {msg}"),
        )

    return {
        "message": "Si cet email existe, un lien de réinitialisation a été envoyé"
    }


@router.post("/password-reset-confirm")
@limiter.limit(RATE_LIMITS["password_reset"])
async def confirm_password_reset(
    request: Request,
    reset: PasswordReset,
    session: Session = Depends(get_session)
):
    """Confirme la réinitialisation : valide le token 'reset' et applique le nouveau
    mot de passe (déverrouille aussi le compte)."""
    payload = decode_token(reset.token)
    verify_token_type(payload, "reset")

    user_id = payload.get("sub")
    user = session.get(User, int(user_id)) if user_id else None
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Utilisateur introuvable.")

    user.usr_password = hash_password(reset.new_password)
    user.updated_at = datetime.utcnow()
    user.failed_login_attempts = 0
    user.locked_until = None
    session.add(user)
    session.commit()

    record_audit(
        "password.reset_confirm", user_id=user.id, user_email=user.email,
        ip_address=(request.client.host if request.client else None),
    )
    return {"message": "Mot de passe réinitialisé avec succès."}
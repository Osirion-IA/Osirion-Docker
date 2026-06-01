from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
import bcrypt as _bcrypt
from app.config import settings
from fastapi import HTTPException, status
import secrets

def hash_password(password: str) -> str:
    return _bcrypt.hashpw(password.encode("utf-8"), _bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return _bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))


# ─────────────────────────────────────────────
# CRÉATION ET VÉRIFICATION DES TOKENS JWT
# ─────────────────────────────────────────────

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Crée un token JWT d'accès.
    
    Args:
        data: Données à encoder dans le token (doit contenir 'sub')
        expires_delta: Durée de validité personnalisée
        
    Returns:
        Token JWT encodé
    """
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({
        "exp": expire,
        "iat": datetime.utcnow(),
        "type": "access"
    })
    
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


def create_refresh_token(data: dict) -> str:
    """
    Crée un token JWT de rafraîchissement.
    
    Args:
        data: Données à encoder dans le token
        
    Returns:
        Token JWT encodé
    """
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    
    to_encode.update({
        "exp": expire,
        "iat": datetime.utcnow(),
        "type": "refresh",
        "jti": secrets.token_urlsafe(32)  # Identifiant unique du token
    })
    
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


def decode_token(token: str) -> dict:
    """
    Décode et valide un token JWT.
    
    Args:
        token: Token JWT à décoder
        
    Returns:
        Payload du token
        
    Raises:
        HTTPException: Si le token est invalide ou expiré
    """
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expiré",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalide",
            headers={"WWW-Authenticate": "Bearer"},
        )


def verify_token_type(payload: dict, expected_type: str) -> None:
    """
    Vérifie que le token est du bon type.
    
    Args:
        payload: Payload décodé du token
        expected_type: Type attendu ("access" ou "refresh")
        
    Raises:
        HTTPException: Si le type ne correspond pas
    """
    token_type = payload.get("type")
    if token_type != expected_type:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Type de token invalide. Attendu: {expected_type}, Reçu: {token_type}",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ─────────────────────────────────────────────
# UTILITAIRES DE SÉCURITÉ
# ─────────────────────────────────────────────

def generate_verification_token() -> str:
    """Génère un token de vérification d'email sécurisé."""
    return secrets.token_urlsafe(32)


def is_account_locked(user) -> bool:
    """
    Vérifie si un compte est verrouillé.
    
    Args:
        user: Instance du modèle User
        
    Returns:
        True si le compte est verrouillé, False sinon
    """
    if user.locked_until is None:
        return False
    return datetime.utcnow() < user.locked_until


def should_lock_account(failed_attempts: int, max_attempts: int = 5) -> bool:
    """
    Détermine si un compte doit être verrouillé.
    
    Args:
        failed_attempts: Nombre de tentatives échouées
        max_attempts: Nombre maximum de tentatives autorisées
        
    Returns:
        True si le compte doit être verrouillé
    """
    return failed_attempts >= max_attempts


def calculate_lock_duration(failed_attempts: int) -> timedelta:
    """
    Calcule la durée de verrouillage en fonction des tentatives échouées.
    
    Args:
        failed_attempts: Nombre de tentatives échouées
        
    Returns:
        Durée de verrouillage
    """
    # Verrouillage progressif : 15min, 30min, 1h, 2h, 24h
    durations = [15, 30, 60, 120, 1440]
    index = min(failed_attempts - 5, len(durations) - 1)
    return timedelta(minutes=durations[index])
from pydantic import BaseModel, EmailStr, Field, validator
from typing import Optional
from datetime import datetime
from app.models.users import UserRole

# ─────────────────────────────────────────────
# SCHÉMAS D'AUTHENTIFICATION
# ─────────────────────────────────────────────

class UserRegister(BaseModel):
    """Schéma pour l'inscription d'un nouvel utilisateur"""
    fullName: str = Field(..., min_length=2, max_length=80)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=100)
    
    @validator('password')
    def validate_password(cls, v):
        """Valide la force du mot de passe"""
        if len(v) < 8:
            raise ValueError('Le mot de passe doit contenir au moins 8 caractères')
        if not any(c.isupper() for c in v):
            raise ValueError('Le mot de passe doit contenir au moins une majuscule')
        if not any(c.islower() for c in v):
            raise ValueError('Le mot de passe doit contenir au moins une minuscule')
        if not any(c.isdigit() for c in v):
            raise ValueError('Le mot de passe doit contenir au moins un chiffre')
        return v


class UserLogin(BaseModel):
    """Schéma pour la connexion"""
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    """Réponse contenant les tokens"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # en secondes


class TokenRefresh(BaseModel):
    """Schéma pour le rafraîchissement du token"""
    refresh_token: str


class TokenData(BaseModel):
    """Données extraites du token"""
    user_id: Optional[int] = None
    email: Optional[str] = None
    role: Optional[str] = None


# ─────────────────────────────────────────────
# SCHÉMAS UTILISATEUR
# ─────────────────────────────────────────────

class UserBase(BaseModel):
    """Informations de base d'un utilisateur"""
    fullName: str
    email: EmailStr
    role: UserRole


class UserCreate(UserBase):
    """Création d'utilisateur (admin uniquement)"""
    password: str = Field(..., min_length=8)


class UserUpdate(BaseModel):
    """Mise à jour d'utilisateur"""
    fullName: Optional[str] = None
    email: Optional[EmailStr] = None
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None


class UserRead(BaseModel):
    """Lecture d'utilisateur (réponse API)"""
    id: int
    fullName: str
    email: EmailStr
    role: str
    is_active: bool
    is_verified: bool
    created_at: datetime
    last_login: Optional[datetime]
    
    class Config:
        from_attributes = True


class UserProfile(BaseModel):
    """Profil utilisateur complet"""
    id: int
    fullName: str
    email: EmailStr
    role: str
    is_active: bool
    is_verified: bool
    created_at: datetime
    updated_at: Optional[datetime]
    last_login: Optional[datetime]
    
    class Config:
        from_attributes = True


class PasswordChange(BaseModel):
    """Changement de mot de passe"""
    old_password: str
    new_password: str = Field(..., min_length=8)
    
    @validator('new_password')
    def validate_new_password(cls, v, values):
        """Valide que le nouveau mot de passe est différent"""
        if 'old_password' in values and v == values['old_password']:
            raise ValueError('Le nouveau mot de passe doit être différent de l\'ancien')
        # Validation de la force (même logique que UserRegister)
        if not any(c.isupper() for c in v):
            raise ValueError('Le mot de passe doit contenir au moins une majuscule')
        if not any(c.islower() for c in v):
            raise ValueError('Le mot de passe doit contenir au moins une minuscule')
        if not any(c.isdigit() for c in v):
            raise ValueError('Le mot de passe doit contenir au moins un chiffre')
        return v


class PasswordResetRequest(BaseModel):
    """Demande de réinitialisation de mot de passe"""
    email: EmailStr


class PasswordReset(BaseModel):
    """Réinitialisation de mot de passe"""
    token: str
    new_password: str = Field(..., min_length=8)
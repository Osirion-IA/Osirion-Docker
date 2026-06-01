from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import datetime
from enum import Enum

class UserRole(str, Enum):
    """Rôles utilisateur disponibles"""
    ADMIN = "admin"       # Accès complet
    USER = "user"         # Accès standard
    VIEWER = "viewer"     # Lecture seule

class User(SQLModel, table=True):
    __tablename__ = "user"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    fullName: str = Field(..., max_length=80)
    email: str = Field(..., max_length=100, unique=True, index=True)
    usr_password: str = Field(..., description="Mot de passe hashé")
    
    # Système de rôles
    role: str = Field(default=UserRole.VIEWER, max_length=20)
    
    # Statut du compte
    is_active: bool = Field(default=True)
    is_verified: bool = Field(default=False)
    
    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = Field(default=None)
    last_login: Optional[datetime] = Field(default=None)
    
    # Sécurité
    failed_login_attempts: int = Field(default=0)
    locked_until: Optional[datetime] = Field(default=None)

class RefreshToken(SQLModel, table=True):
    __tablename__ = "refresh_tokens"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    token: str = Field(..., unique=True, index=True)
    
    # Métadonnées
    expires_at: datetime
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Sécurité
    is_revoked: bool = Field(default=False)
    device_info: Optional[str] = Field(default=None, max_length=255)
    ip_address: Optional[str] = Field(default=None, max_length=45)
# app/models/audit.py
"""
Journal d'audit — trace les actions sensibles (connexions, gestion utilisateurs,
mises sous surveillance, notifications…).

Table additive et indépendante : son écriture est best-effort (cf. audit_service)
et ne doit jamais faire échouer l'action métier qu'elle journalise.
"""
from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import datetime


class AuditLog(SQLModel, table=True):
    __tablename__ = "audit_log"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: Optional[int] = Field(default=None, index=True)
    user_email: Optional[str] = Field(default=None, max_length=120)
    action: str = Field(..., max_length=60, index=True)     # ex. "login.success", "user.delete"
    target_type: Optional[str] = Field(default=None, max_length=40)
    target_id: Optional[str] = Field(default=None, max_length=60)
    detail: Optional[str] = Field(default=None, max_length=512)
    ip_address: Optional[str] = Field(default=None, max_length=45)
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)

# app/routes/audit_routes.py
"""Consultation du journal d'audit (admin uniquement)."""
from fastapi import APIRouter, Depends
from sqlmodel import Session, select
from typing import Optional

from app.database import get_session
from app.models.audit import AuditLog
from app.middleware.auth_middleware import require_admin

router = APIRouter()


@router.get("/")
def list_audit(
    action: Optional[str] = None,
    skip: int = 0,
    limit: int = 200,
    _current_user=Depends(require_admin),
    session: Session = Depends(get_session),
):
    stmt = select(AuditLog)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    stmt = stmt.order_by(AuditLog.id.desc()).offset(skip).limit(limit)
    return session.exec(stmt).all()

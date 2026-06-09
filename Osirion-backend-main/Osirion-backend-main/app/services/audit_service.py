# app/services/audit_service.py
"""
Écriture du journal d'audit — BEST-EFFORT.

`record_audit` ouvre sa propre session (indépendante de la transaction métier) et
avale toute exception : journaliser une action ne doit JAMAIS faire échouer
l'action elle-même (connexion, suppression d'utilisateur, etc.).
"""
import logging
from typing import Optional

from sqlmodel import Session
from app.database import engine
from app.models.audit import AuditLog

logger = logging.getLogger(__name__)


def record_audit(
    action: str,
    user_id: Optional[int] = None,
    user_email: Optional[str] = None,
    target_type: Optional[str] = None,
    target_id=None,
    detail: Optional[str] = None,
    ip_address: Optional[str] = None,
) -> None:
    try:
        with Session(engine) as session:
            session.add(AuditLog(
                action=action,
                user_id=user_id,
                user_email=user_email,
                target_type=target_type,
                target_id=None if target_id is None else str(target_id),
                detail=(detail[:512] if detail else None),
                ip_address=ip_address,
            ))
            session.commit()
    except Exception as e:
        # Ne jamais propager : l'audit est secondaire par rapport à l'action métier.
        logger.warning(f"[audit] écriture ignorée (non bloquant) : {e}")

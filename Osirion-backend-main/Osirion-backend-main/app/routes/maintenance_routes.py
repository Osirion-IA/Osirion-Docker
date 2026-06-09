# app/routes/maintenance_routes.py
"""
Maintenance / rétention des données (admin uniquement).

La purge est une action MANUELLE et destructive : elle n'est JAMAIS déclenchée
automatiquement. Un endpoint d'aperçu permet de voir l'impact avant de purger.
"""
from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, select
from sqlalchemy import func
from datetime import datetime, timedelta
from pathlib import Path
import logging

from app.database import get_session
from app.models.events import Event
from app.middleware.auth_middleware import require_admin
from app.services.audit_service import record_audit

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/purge-preview")
def purge_preview(
    days: int = Query(90, ge=1, le=3650),
    _current_user=Depends(require_admin),
    session: Session = Depends(get_session),
):
    """Combien d'événements seraient supprimés (sans rien supprimer)."""
    cutoff = datetime.utcnow() - timedelta(days=days)
    to_delete = session.exec(
        select(func.count()).select_from(Event).where(Event.timestamp < cutoff)
    ).one()
    total = session.exec(select(func.count()).select_from(Event)).one()
    return {"older_than_days": days, "to_delete": int(to_delete), "total_events": int(total)}


@router.post("/purge-events")
def purge_events(
    days: int = Query(90, ge=1, le=3650),
    current_user=Depends(require_admin),
    session: Session = Depends(get_session),
):
    """Supprime les événements antérieurs à `days` jours + leurs snapshots disque.

    ⚠️ Destructif et irréversible — action manuelle explicite de l'admin."""
    cutoff = datetime.utcnow() - timedelta(days=days)
    old = session.exec(select(Event).where(Event.timestamp < cutoff)).all()

    deleted = files_removed = 0
    for ev in old:
        if ev.snapshot_url:
            try:
                p = Path(str(ev.snapshot_url).lstrip("/"))
                if p.exists() and p.is_file():
                    p.unlink()
                    files_removed += 1
            except Exception:
                pass  # best-effort sur le fichier
        session.delete(ev)
        deleted += 1
    session.commit()

    record_audit(
        "maintenance.purge_events",
        user_id=getattr(current_user, "id", None),
        user_email=getattr(current_user, "email", None),
        detail=f"days={days} events={deleted} snapshots={files_removed}",
    )
    logger.info(f"[maintenance] purge < {days}j : {deleted} événements, {files_removed} snapshots")
    return {"deleted_events": deleted, "removed_snapshots": files_removed, "older_than_days": days}

# app/routes/maintenance_routes.py
"""
Maintenance / rétention des données (admin uniquement).

La purge exposée ici reste une action MANUELLE et destructive, avec un endpoint
d'aperçu pour en mesurer l'impact avant de la déclencher.

Elle n'est plus la seule voie : depuis le constat de saturation disque de la
campagne d'août 2026 (~800 Mo de captures par jour, partition pleine en une
vingtaine de jours), une rétention AUTOMATIQUE tourne en tâche de fond — voir
`app.services.retention_scheduler`, piloté par RETENTION_DAYS. Les deux voies
partagent la même implémentation de suppression.
"""
from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, select
from sqlalchemy import func
from datetime import datetime, timedelta
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
    # Implémentation partagée avec la rétention automatique : une seule logique de
    # suppression, donc un seul comportement à vérifier (cf. retention_scheduler).
    from app.services.retention_scheduler import purge_older_than

    stats = purge_older_than(session, days)
    deleted, files_removed = stats["deleted_events"], stats["removed_snapshots"]

    record_audit(
        "maintenance.purge_events",
        user_id=getattr(current_user, "id", None),
        user_email=getattr(current_user, "email", None),
        detail=f"days={days} events={deleted} snapshots={files_removed}",
    )
    logger.info(f"[maintenance] purge < {days}j : {deleted} événements, {files_removed} snapshots")
    return {"deleted_events": deleted, "removed_snapshots": files_removed, "older_than_days": days}


@router.get("/disk")
def disk(_current_user=Depends(require_admin)):
    """Espace disque de la partition qui porte les captures, et état de la rétention.

    La campagne d'août 2026 s'est déroulée sans aucune visibilité sur ce point :
    la saturation approchait sans que rien ne le signale. Cet endpoint alimente
    l'écran d'exploitation et sert de contrôle avant de lancer une campagne.
    """
    from app.config import settings
    from app.services.retention_scheduler import disk_usage, is_running

    espace = disk_usage()
    jours = int(getattr(settings, "RETENTION_DAYS", 0) or 0)
    seuil = float(getattr(settings, "RETENTION_MIN_FREE_GB", 10) or 10)
    return {
        **espace,
        "retention_days": jours,
        "retention_running": is_running(),
        "min_free_gb": seuil,
        "below_threshold": espace["free_gb"] < seuil,
    }

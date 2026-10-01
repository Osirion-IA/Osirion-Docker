# app/routes/dashboard_routes.py
"""
Agrégats pour le tableau de bord (KPI réels).

Une seule requête côté frontend → compteurs + répartition par type d'événement
+ série temporelle (7 derniers jours). Lecture seule, accessible à tous les rôles.
"""
from fastapi import APIRouter, Depends
from sqlmodel import Session, select
from sqlalchemy import func
from datetime import datetime, timedelta
import logging

from app.database import get_session
from app.models.events import Event
from app.models.cameras import Camera
from app.models.alerts import Alert, ALERT_NEW
from app.middleware.auth_middleware import require_viewer

router = APIRouter()
logger = logging.getLogger(__name__)


def _count(session: Session, model, *conditions) -> int:
    stmt = select(func.count()).select_from(model)
    for c in conditions:
        stmt = stmt.where(c)
    return int(session.exec(stmt).one())


@router.get("/")
def dashboard(
    days: int = 7,
    _current_user=Depends(require_viewer),
    session: Session = Depends(get_session),
):
    days = max(1, min(days, 90))

    counts = {
        "cameras": _count(session, Camera),
        "events_total": _count(session, Event),
        "alerts_total": _count(session, Alert),
        "alerts_new": _count(session, Alert, Alert.status == ALERT_NEW),
    }

    # Répartition par type d'événement.
    by_type_rows = session.exec(
        select(Event.event_type, func.count()).group_by(Event.event_type)
    ).all()
    events_by_type = {str(t): int(n) for t, n in by_type_rows}

    # Série temporelle : événements par jour sur la fenêtre demandée.
    since = datetime.utcnow().date() - timedelta(days=days - 1)
    day_rows = session.exec(
        select(func.date(Event.timestamp), func.count())
        .where(Event.timestamp >= datetime.combine(since, datetime.min.time()))
        .group_by(func.date(Event.timestamp))
    ).all()
    by_day_map = {str(d): int(n) for d, n in day_rows}

    events_by_day = []
    for i in range(days):
        d = since + timedelta(days=i)
        key = d.isoformat()
        events_by_day.append({"date": key, "count": by_day_map.get(key, 0)})

    return {
        "counts": counts,
        "events_by_type": events_by_type,
        "events_by_day": events_by_day,
    }

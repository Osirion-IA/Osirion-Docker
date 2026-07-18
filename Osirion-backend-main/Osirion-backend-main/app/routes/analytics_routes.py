# app/routes/analytics_routes.py
"""
Analytics Engine — agrégats opérationnels calculés À LA VOLÉE depuis la table
`event` (qui contient déjà des agrégats discrets throttlés). Toujours frais, pas
de table pré-agrégée pour l'instant (volume prototype ; la pré-agrégation
`analytics_kpi` + jobs de fond est le chemin de montée en charge).

Endpoints (VIEWER+) :
  - /analytics/footfall  : entrées / sorties / net par jour (LINE_CROSSED)
  - /analytics/occupancy : occupation par zone (ZONE_OCCUPANCY_CHANGED)
  - /analytics/queues    : files (longueur + temps d'attente) (occupation + ZONE_DWELL)
  - /analytics/summary   : KPIs du jour (dashboard opérationnel)
"""
from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, select
from typing import Optional
from datetime import datetime, timedelta
from collections import defaultdict

from app.database import get_session
from app.models.events import (
    Event,
    EVENT_LINE_CROSSED,
    EVENT_ZONE_OCCUPANCY_CHANGED,
    EVENT_ZONE_DWELL,
    EVENT_CROWD_DETECTED,
)
from app.models.zones import Zone, ZONE_QUEUE
from app.models.users import User
from app.middleware.auth_middleware import require_viewer

router = APIRouter()


def _events(session: Session, event_type: str, since: datetime, camera_id: Optional[int] = None):
    stmt = select(Event).where(Event.event_type == event_type, Event.timestamp >= since)
    if camera_id is not None:
        stmt = stmt.where(Event.camera_id == camera_id)
    return session.exec(stmt.order_by(Event.timestamp)).all()


@router.get("/footfall")
def footfall(
    days: int = Query(7, ge=1, le=90),
    camera_id: Optional[int] = None,
    _user: User = Depends(require_viewer),
    session: Session = Depends(get_session),
):
    """Entrées / sorties / net par jour (depuis LINE_CROSSED, meta.direction)."""
    since_date = datetime.utcnow().date() - timedelta(days=days - 1)
    since_dt = datetime.combine(since_date, datetime.min.time())
    rows = _events(session, EVENT_LINE_CROSSED, since_dt, camera_id)

    per_day = defaultdict(lambda: {"entries": 0, "exits": 0})
    for e in rows:
        d = e.timestamp.date().isoformat()
        direction = (e.meta or {}).get("direction")
        if direction == "in":
            per_day[d]["entries"] += 1
        elif direction == "out":
            per_day[d]["exits"] += 1

    series = []
    for i in range(days):
        d = (since_date + timedelta(days=i)).isoformat()
        en, ex = per_day[d]["entries"], per_day[d]["exits"]
        series.append({"date": d, "entries": en, "exits": ex, "net": en - ex})

    total_in = sum(s["entries"] for s in series)
    total_out = sum(s["exits"] for s in series)
    return {
        "days": days,
        "total_entries": total_in,
        "total_exits": total_out,
        "present_estimate": total_in - total_out,
        "series": series,
    }


@router.get("/occupancy")
def occupancy(
    hours: int = Query(24, ge=1, le=168),
    zone_id: Optional[int] = None,
    _user: User = Depends(require_viewer),
    session: Session = Depends(get_session),
):
    """Avec zone_id : série temporelle + moy/max/actuel. Sans : dernière
    occupation connue par zone (fenêtre `hours`)."""
    since = datetime.utcnow() - timedelta(hours=hours)
    rows = _events(session, EVENT_ZONE_OCCUPANCY_CHANGED, since)

    if zone_id is not None:
        pts = [
            {"t": e.timestamp.isoformat(), "count": (e.meta or {}).get("count", 0)}
            for e in rows if (e.meta or {}).get("zone_id") == zone_id
        ]
        counts = [p["count"] for p in pts]
        return {
            "zone_id": zone_id,
            "series": pts,
            "avg": round(sum(counts) / len(counts), 2) if counts else 0,
            "max": max(counts) if counts else 0,
            "current": counts[-1] if counts else 0,
        }

    latest = {}
    for e in rows:
        zid = (e.meta or {}).get("zone_id")
        if zid is not None:
            latest[zid] = {
                "zone_id": zid,
                "zone_name": (e.meta or {}).get("zone_name"),
                "count": (e.meta or {}).get("count", 0),
                "t": e.timestamp.isoformat(),
            }
    return {"zones": list(latest.values())}


@router.get("/queues")
def queues(
    hours: int = Query(24, ge=1, le=168),
    _user: User = Depends(require_viewer),
    session: Session = Depends(get_session),
):
    """Par zone de type « file » : longueur actuelle + temps d'attente moy/max."""
    qzones = session.exec(select(Zone).where(Zone.kind == ZONE_QUEUE)).all()
    if not qzones:
        return {"queues": []}

    since = datetime.utcnow() - timedelta(hours=hours)
    occ = _events(session, EVENT_ZONE_OCCUPANCY_CHANGED, since)
    dwell = _events(session, EVENT_ZONE_DWELL, since)

    last_len = {}
    for e in occ:
        zid = (e.meta or {}).get("zone_id")
        if zid is not None:
            last_len[zid] = (e.meta or {}).get("count", 0)

    waits = defaultdict(list)
    for e in dwell:
        zid = (e.meta or {}).get("zone_id")
        w = (e.meta or {}).get("dwell_s")
        if zid is not None and w is not None:
            waits[zid].append(w)

    out = []
    for z in qzones:
        ws = waits.get(z.id, [])
        out.append({
            "zone_id": z.id,
            "name": z.name,
            "camera_id": z.camera_id,
            "length": last_len.get(z.id, 0),
            "wait_avg_s": round(sum(ws) / len(ws), 1) if ws else 0,
            "wait_max_s": round(max(ws), 1) if ws else 0,
            "samples": len(ws),
        })
    return {"queues": out}


@router.get("/summary")
def summary(_user: User = Depends(require_viewer), session: Session = Depends(get_session)):
    """KPIs du jour pour le dashboard opérationnel."""
    today = datetime.combine(datetime.utcnow().date(), datetime.min.time())
    since24 = datetime.utcnow() - timedelta(hours=24)

    lines = _events(session, EVENT_LINE_CROSSED, today)
    entries = sum(1 for e in lines if (e.meta or {}).get("direction") == "in")
    exits = sum(1 for e in lines if (e.meta or {}).get("direction") == "out")
    crowd = len(_events(session, EVENT_CROWD_DETECTED, today))

    occ = _events(session, EVENT_ZONE_OCCUPANCY_CHANGED, since24)
    latest = {}
    for e in occ:
        zid = (e.meta or {}).get("zone_id")
        if zid is not None:
            latest[zid] = (e.meta or {}).get("count", 0)
    current_occupancy = sum(latest.values())

    dwell = _events(session, EVENT_ZONE_DWELL, today)
    qids = {z.id for z in session.exec(select(Zone).where(Zone.kind == ZONE_QUEUE)).all()}
    qwaits = [
        (e.meta or {}).get("dwell_s") for e in dwell
        if (e.meta or {}).get("zone_id") in qids and (e.meta or {}).get("dwell_s") is not None
    ]

    return {
        "entries_today": entries,
        "exits_today": exits,
        "present_now_estimate": entries - exits,
        "current_occupancy": current_occupancy,
        "crowd_alerts_today": crowd,
        "avg_wait_s": round(sum(qwaits) / len(qwaits), 1) if qwaits else 0,
    }

# app/routes/camera_status_routes.py
"""
Historique de connectivité & disponibilité des caméras.

Reconstitue, à partir des TRANSITIONS d'état persistées (camera_status_event) :
disponibilité (uptime %), nombre de déconnexions, temps total hors-ligne, plus
longue coupure, reconnexions — globalement et par caméra, filtrable par période,
agence (groupe) et caméra.

Endpoints (VIEWER+) :
  - GET /camera-status/history : liste des transitions (journal).
  - GET /camera-status/stats   : statistiques de disponibilité (agrégées + par caméra).
"""
from typing import Optional
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, select, text
from sqlalchemy.orm import selectinload

from app.database import get_session
from app.models.camera_status_event import CameraStatusEvent
from app.models.cameras import Camera
from app.models.users import User
from app.middleware.auth_middleware import require_viewer
from app.services.response_cache import cached_endpoint

router = APIRouter()


def _metrics(evs, start_state, since, now):
    """Reconstruit les intervalles d'état sur [since, now] → métriques de dispo.

    evs : transitions (asc) dans la fenêtre. start_state : état à `since`
    (dernière transition antérieure). Les périodes hors-ligne CONTIGUËS
    (offline/connecting/stalled/stopped) sont comptées comme UNE coupure.
    """
    online = 0.0
    outages = []          # durées des périodes hors-ligne contiguës
    cur_outage = 0.0
    in_outage = False
    reconnections = 0

    cursor_t = since
    cursor_s = start_state
    if cursor_s is None and evs:          # état initial inconnu → on démarre au 1er évènement
        cursor_t = evs[0].timestamp
        cursor_s = evs[0].status
        evs = evs[1:]

    def add_time(state, dur):
        nonlocal online, cur_outage, in_outage
        if dur <= 0:
            return
        if state == "online":
            online += dur
        elif state is not None:
            cur_outage += dur
            in_outage = True

    def close_outage():
        nonlocal cur_outage, in_outage
        if in_outage:
            outages.append(cur_outage)
            cur_outage = 0.0
            in_outage = False

    for e in evs:
        add_time(cursor_s, (e.timestamp - cursor_t).total_seconds())
        if e.status == "online" and cursor_s not in (None, "online"):
            reconnections += 1
            close_outage()
        cursor_t = e.timestamp
        cursor_s = e.status
    add_time(cursor_s, (now - cursor_t).total_seconds())
    close_outage()

    observed = online + sum(outages)
    return {
        "current_status": cursor_s,
        "uptime_pct": round(100 * online / observed, 1) if observed > 0 else None,
        "online_seconds": round(online),
        "offline_seconds": round(sum(outages)),
        "disconnections": len(outages),         # nb de périodes hors-ligne
        "reconnections": reconnections,
        "longest_outage_seconds": round(max(outages)) if outages else 0,
    }


def _targets(session, group_id, camera_id):
    """(meta par caméra, ensemble de caméras ciblées | None si toutes)."""
    cams = session.exec(select(Camera).options(selectinload(Camera.groups))).all()
    meta = {c.id: {"name": c.cam_name, "site": (c.groups[0].name if c.groups else None),
                   "gids": [g.id for g in c.groups]} for c in cams}
    target = None
    if camera_id is not None:
        target = {camera_id}
    elif group_id is not None:
        target = {cid for cid, m in meta.items() if group_id in m["gids"]}
    return meta, target


@router.get("/stats")
@cached_endpoint("camera-status:stats", 30)
def stats(
    days: int = Query(7, ge=1, le=90),
    group_id: Optional[int] = None,
    camera_id: Optional[int] = None,
    _user: User = Depends(require_viewer),
    session: Session = Depends(get_session),
):
    now = datetime.utcnow()
    since = now - timedelta(days=days)
    meta, target = _targets(session, group_id, camera_id)

    # Transitions dans la fenêtre.
    stmt = select(CameraStatusEvent).where(CameraStatusEvent.timestamp >= since)
    if target is not None:
        stmt = stmt.where(CameraStatusEvent.camera_id.in_(target))
    ev_in = session.exec(stmt.order_by(CameraStatusEvent.camera_id, CameraStatusEvent.timestamp)).all()

    # État à `since` = dernière transition ANTÉRIEURE, par caméra (DISTINCT ON).
    prior_rows = session.exec(text(
        "SELECT DISTINCT ON (camera_id) camera_id, status FROM camera_status_event "
        "WHERE timestamp < :since ORDER BY camera_id, timestamp DESC"
    ).bindparams(since=since)).all()
    prior = {row[0]: row[1] for row in prior_rows}

    by_cam = {}
    for e in ev_in:
        by_cam.setdefault(e.camera_id, []).append(e)

    cam_ids = set(by_cam) | set(prior.keys())
    if target is not None:
        cam_ids &= target

    rows = []
    for cid in cam_ids:
        evs = by_cam.get(cid, [])
        start_state = prior.get(cid) or (evs[0].prev_status if evs else None)
        m = _metrics(evs, start_state, since, now)
        info = meta.get(cid, {})
        rows.append({"camera_id": cid, "name": info.get("name") or f"Caméra {cid}",
                     "site": info.get("site"), **m})

    # Tri : les moins disponibles / les plus instables en premier.
    rows.sort(key=lambda r: (r["uptime_pct"] if r["uptime_pct"] is not None else 101,
                             -r["disconnections"]))

    ups = [r["uptime_pct"] for r in rows if r["uptime_pct"] is not None]
    summary = {
        "cameras": len(rows),
        "avg_uptime_pct": round(sum(ups) / len(ups), 1) if ups else None,
        "total_disconnections": sum(r["disconnections"] for r in rows),
        "total_offline_seconds": sum(r["offline_seconds"] for r in rows),
        "currently_offline": sum(1 for r in rows if r["current_status"] not in (None, "online")),
    }

    # Série journalière : déconnexions (→ non-online) et reconnexions (→ online).
    per_day = {}
    for e in ev_in:
        b = per_day.setdefault(e.timestamp.date().isoformat(), {"disconnections": 0, "reconnections": 0})
        if e.status == "online" and e.prev_status not in (None, "online"):
            b["reconnections"] += 1
        elif e.status != "online" and e.prev_status in (None, "online"):
            b["disconnections"] += 1
    daily = []
    dd = since.date()
    while dd <= now.date():
        k = dd.isoformat()
        b = per_day.get(k, {"disconnections": 0, "reconnections": 0})
        daily.append({"date": k, "disconnections": b["disconnections"], "reconnections": b["reconnections"]})
        dd += timedelta(days=1)

    return {"days": days, "summary": summary, "cameras": rows, "daily": daily}


@router.get("/history")
def history(
    camera_id: Optional[int] = None,
    group_id: Optional[int] = None,
    days: int = Query(7, ge=1, le=90),
    limit: int = Query(300, ge=1, le=2000),
    _user: User = Depends(require_viewer),
    session: Session = Depends(get_session),
):
    now = datetime.utcnow()
    since = now - timedelta(days=days)
    meta, target = _targets(session, group_id, camera_id)

    stmt = select(CameraStatusEvent).where(CameraStatusEvent.timestamp >= since)
    if target is not None:
        stmt = stmt.where(CameraStatusEvent.camera_id.in_(target))
    evs = session.exec(stmt.order_by(CameraStatusEvent.timestamp.desc()).limit(limit)).all()

    return {
        "days": days,
        "events": [{
            "id": e.id, "camera_id": e.camera_id,
            "name": (meta.get(e.camera_id) or {}).get("name") or f"Caméra {e.camera_id}",
            "site": (meta.get(e.camera_id) or {}).get("site"),
            "status": e.status, "prev_status": e.prev_status,
            "reconnection_attempts": e.reconnection_attempts,
            "timestamp": e.timestamp.isoformat(),
        } for e in evs],
    }

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

from sqlalchemy.orm import selectinload

from app.database import get_session
from app.models.events import (
    Event,
    EVENT_LINE_CROSSED,
    EVENT_ZONE_OCCUPANCY_CHANGED,
    EVENT_ZONE_DWELL,
    EVENT_CROWD_DETECTED,
)
from app.models.zones import Zone, ZONE_QUEUE
from app.models.cameras import Camera
from app.models.alerts import Alert
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

    # Comparaison à la période PRÉCÉDENTE (même durée, juste avant) → deltas WoW/DoD.
    prev_since_date = since_date - timedelta(days=days)
    prev_since_dt = datetime.combine(prev_since_date, datetime.min.time())
    prev_rows = [e for e in _events(session, EVENT_LINE_CROSSED, prev_since_dt, camera_id)
                 if e.timestamp < since_dt]
    prev_in = sum(1 for e in prev_rows if (e.meta or {}).get("direction") == "in")
    prev_out = sum(1 for e in prev_rows if (e.meta or {}).get("direction") == "out")

    def _pct(cur, prev):
        return round(100 * (cur - prev) / prev) if prev > 0 else None

    return {
        "days": days,
        "total_entries": total_in,
        "total_exits": total_out,
        "present_estimate": total_in - total_out,
        "series": series,
        "previous": {"total_entries": prev_in, "total_exits": prev_out},
        "delta_entries_pct": _pct(total_in, prev_in),
        "delta_exits_pct": _pct(total_out, prev_out),
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


@router.get("/by-camera")
def by_camera(
    days: int = Query(7, ge=1, le=90),
    _user: User = Depends(require_viewer),
    session: Session = Depends(get_session),
):
    """Répartition SPATIALE de l'affluence : entrées/sorties + occupation courante
    par caméra, et agrégat par site (groupe). Répond à « quelle agence / caméra
    est la plus fréquentée ? »."""
    since_date = datetime.utcnow().date() - timedelta(days=days - 1)
    since_dt = datetime.combine(since_date, datetime.min.time())
    lines = _events(session, EVENT_LINE_CROSSED, since_dt)
    occ = _events(session, EVENT_ZONE_OCCUPANCY_CHANGED, since_dt)

    per_cam = defaultdict(lambda: {"entries": 0, "exits": 0})
    for e in lines:
        direction = (e.meta or {}).get("direction")
        if direction == "in":
            per_cam[e.camera_id]["entries"] += 1
        elif direction == "out":
            per_cam[e.camera_id]["exits"] += 1

    # Occupation courante par caméra = somme de la dernière occupation connue de ses zones.
    latest_zone = {}
    for e in occ:
        zid = (e.meta or {}).get("zone_id")
        if zid is not None:
            latest_zone[zid] = (e.camera_id, (e.meta or {}).get("count", 0))
    occ_per_cam = defaultdict(int)
    for _zid, (cid, cnt) in latest_zone.items():
        occ_per_cam[cid] += cnt

    cams = session.exec(select(Camera).options(selectinload(Camera.groups))).all()
    cam_meta = {c.id: {"name": c.cam_name, "site": (c.groups[0].name if c.groups else None)} for c in cams}

    rows = []
    for cid in set(per_cam) | set(occ_per_cam):
        m = cam_meta.get(cid, {})
        rows.append({
            "camera_id": cid,
            "name": m.get("name") or f"Caméra {cid}",
            "site": m.get("site"),
            "entries": per_cam[cid]["entries"],
            "exits": per_cam[cid]["exits"],
            "current_occupancy": occ_per_cam.get(cid, 0),
        })
    rows.sort(key=lambda r: r["entries"], reverse=True)

    site_agg = defaultdict(lambda: {"entries": 0, "cameras": 0})
    for r in rows:
        s = r["site"] or "Sans site"
        site_agg[s]["entries"] += r["entries"]
        site_agg[s]["cameras"] += 1
    sites = [{"site": s, **v} for s, v in site_agg.items()]
    sites.sort(key=lambda r: r["entries"], reverse=True)

    return {"days": days, "cameras": rows, "sites": sites}


@router.get("/incidents")
def incidents(
    days: int = Query(7, ge=1, le=90),
    _user: User = Depends(require_viewer),
    session: Session = Depends(get_session),
):
    """Analyse SÉCURITÉ : attroupements détectés (CROWD_DETECTED) + alertes du
    centre d'alertes — timeline journalière, répartition par sévérité / type /
    caméra, et taux de résolution du workflow."""
    since_date = datetime.utcnow().date() - timedelta(days=days - 1)
    since_dt = datetime.combine(since_date, datetime.min.time())
    crowd = _events(session, EVENT_CROWD_DETECTED, since_dt)
    alerts = session.exec(select(Alert).where(Alert.created_at >= since_dt)).all()

    per_day = defaultdict(lambda: {"crowd": 0, "alerts": 0})
    for e in crowd:
        per_day[e.timestamp.date().isoformat()]["crowd"] += 1
    for a in alerts:
        per_day[a.created_at.date().isoformat()]["alerts"] += 1
    series = []
    for i in range(days):
        dd = (since_date + timedelta(days=i)).isoformat()
        series.append({"date": dd, "crowd": per_day[dd]["crowd"], "alerts": per_day[dd]["alerts"]})

    by_sev = defaultdict(int)
    by_kind = defaultdict(int)
    by_status = defaultdict(int)
    by_cam = defaultdict(int)
    for a in alerts:
        by_sev[a.severity] += 1
        by_kind[a.kind] += 1
        by_status[a.status] += 1
        if a.camera_id is not None:
            by_cam[a.camera_id] += 1

    cams = {c.id: c.cam_name for c in session.exec(select(Camera)).all()}
    by_camera = [{"camera_id": cid, "name": cams.get(cid, f"Caméra {cid}"), "count": n}
                 for cid, n in by_cam.items()]
    by_camera.sort(key=lambda r: r["count"], reverse=True)

    total = len(alerts)
    resolved = by_status.get("resolved", 0)
    return {
        "days": days,
        "crowd_total": len(crowd),
        "alerts_total": total,
        "series": series,
        "by_severity": {k: by_sev.get(k, 0) for k in ("info", "warning", "critical")},
        "by_kind": dict(by_kind),
        "by_status": {k: by_status.get(k, 0) for k in ("new", "acknowledged", "resolved")},
        "resolution_rate": round(100 * resolved / total) if total else None,
        "by_camera": by_camera,
    }


@router.get("/insights")
def insights(
    days: int = Query(30, ge=7, le=180),
    _user: User = Depends(require_viewer),
    session: Session = Depends(get_session),
):
    """Analyse d'affluence EXPLOITABLE pour la décision — à partir des passages
    (LINE_CROSSED, direction=in) sur `days` jours :
      - profil horaire (heures de pointe / creux),
      - heatmap jour de semaine × heure (moyenne par occurrence du jour),
      - jour le plus chargé,
      - projection de fin de journée + prévision des prochaines heures, à partir
        de la BASELINE historique par (jour de semaine, heure) — statistique, pas
        de ML. Un indice de `confidence` évite de sur-interpréter peu de données.
    """
    now = datetime.utcnow()
    since_date = now.date() - timedelta(days=days - 1)
    since_dt = datetime.combine(since_date, datetime.min.time())
    lines = _events(session, EVENT_LINE_CROSSED, since_dt)

    HOURS = list(range(24))
    # Nombre d'occurrences de chaque jour de semaine dans la fenêtre (pour moyenner).
    weekday_occ = defaultdict(int)
    d = since_date
    while d <= now.date():
        weekday_occ[d.weekday()] += 1
        d += timedelta(days=1)

    per_hour_in = defaultdict(int)
    per_hour_out = defaultdict(int)
    per_wh_in = defaultdict(int)        # (weekday, hour) -> entrées
    weekday_totals = defaultdict(int)   # weekday -> entrées
    active_days = set()
    today = now.date()
    today_hour_in = defaultdict(int)

    for e in lines:
        direction = (e.meta or {}).get("direction")
        ts = e.timestamp
        h, wd, dd = ts.hour, ts.weekday(), ts.date()
        if direction == "in":
            per_hour_in[h] += 1
            per_wh_in[(wd, h)] += 1
            weekday_totals[wd] += 1
            active_days.add(dd)
            if dd == today:
                today_hour_in[h] += 1
        elif direction == "out":
            per_hour_out[h] += 1

    total_in = sum(per_hour_in.values())
    n_active_days = max(1, len(active_days))

    hourly = [{
        "hour": h,
        "entries": per_hour_in.get(h, 0),
        "exits": per_hour_out.get(h, 0),
        "avg_entries": round(per_hour_in.get(h, 0) / n_active_days, 1),
    } for h in HOURS]

    peak_hour = max(HOURS, key=lambda h: per_hour_in.get(h, 0)) if total_in else None
    biz = [h for h in HOURS if 6 <= h <= 22]
    quietest_hour = min(biz, key=lambda h: per_hour_in.get(h, 0)) if total_in else None

    weekday_avg = {wd: round(weekday_totals.get(wd, 0) / max(1, weekday_occ.get(wd, 1)), 1) for wd in range(7)}
    busiest_weekday = max(range(7), key=lambda wd: weekday_avg[wd]) if total_in else None

    # Heatmap : moyenne d'entrées par occurrence du jour.
    heatmap = [[round(per_wh_in.get((wd, h), 0) / max(1, weekday_occ.get(wd, 1)), 1) for h in HOURS] for wd in range(7)]
    heatmap_max = max((max(row) for row in heatmap), default=0)

    # Baseline pour AUJOURD'HUI (même jour de semaine, en excluant aujourd'hui).
    twd = today.weekday()
    base_occ = max(1, weekday_occ.get(twd, 1) - 1)
    baseline_hour = {h: (per_wh_in.get((twd, h), 0) - today_hour_in.get(h, 0)) / base_occ for h in HOURS}
    cur_hour = now.hour
    today_so_far = sum(today_hour_in.values())
    expected_so_far = sum(v for h, v in baseline_hour.items() if h <= cur_hour)
    projected_eod = round(today_so_far + sum(v for h, v in baseline_hour.items() if h > cur_hour))
    vs_avg_pct = round(100 * (today_so_far - expected_so_far) / expected_so_far) if expected_so_far > 0.5 else None

    forecast = [{"hour": h, "expected": round(baseline_hour[h])} for h in HOURS if cur_hour < h <= cur_hour + 3]

    confidence = (
        "high" if (n_active_days >= 14 and total_in >= 200)
        else "medium" if (n_active_days >= 4 and total_in >= 40)
        else "low"
    )

    return {
        "days": days,
        "total_entries": total_in,
        "active_days": len(active_days),
        "hourly": hourly,
        "peak_hour": peak_hour,
        "peak_hour_count": per_hour_in.get(peak_hour, 0) if peak_hour is not None else 0,
        "quietest_hour": quietest_hour,
        "weekday_avg": weekday_avg,
        "busiest_weekday": busiest_weekday,
        "heatmap": heatmap,
        "heatmap_max": heatmap_max,
        "today": {
            "so_far": today_so_far,
            "expected_so_far": round(expected_so_far, 1),
            "projected_eod": projected_eod,
            "vs_avg_pct": vs_avg_pct,
        },
        "forecast": forecast,
        "confidence": confidence,
    }

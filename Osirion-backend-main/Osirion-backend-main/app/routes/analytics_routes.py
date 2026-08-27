# app/routes/analytics_routes.py
"""
Analytics Engine — agrégats opérationnels calculés À LA VOLÉE depuis la table
`event` (qui contient déjà des agrégats discrets throttlés). Toujours frais, pas
de table pré-agrégée pour l'instant (volume prototype ; la pré-agrégation
`analytics_kpi` + jobs de fond est le chemin de montée en charge).

Endpoints (VIEWER+) :
  - /analytics/footfall  : entrées / sorties / net par jour (LINE_CROSSED)
  - /analytics/occupancy : occupation par zone (ZONE_OCCUPANCY_CHANGED)
  - /analytics/queue-affluence / queue-performance : affluence & attente des FILES
  - /analytics/post-absence : épisodes et durées d'absence aux postes
  - /analytics/staffing     : épisodes de sous-effectif par caméra
  - /analytics/summary   : KPIs du jour (dashboard opérationnel)
"""
from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, select
from typing import Optional
from datetime import datetime, timedelta
from collections import defaultdict
import math

from sqlalchemy.orm import selectinload

from app.database import get_session
from app.models.events import (
    Event,
    EVENT_LINE_CROSSED,
    EVENT_ZONE_OCCUPANCY_CHANGED,
    EVENT_ZONE_DWELL,
    EVENT_CROWD_DETECTED,
    EVENT_POST_VACANT,
    EVENT_POST_ABSENCE,
    EVENT_STAFFING_LOW,
    EVENT_STAFFING_RECOVERED,
)
from app.models.zones import Zone, ZONE_QUEUE
from app.models.cameras import Camera
from app.models.work_schedule import WorkSchedule
from app.models.alerts import Alert
from app.models.users import User
from app.middleware.auth_middleware import require_viewer
from app.services.response_cache import cache_get_or_set, cached_endpoint
from app.routes.camera_status_routes import stats as camera_status_stats

router = APIRouter()


def _seconds(value) -> float:
    """Normalise une durée issue d'un JSON historique sans casser l'endpoint."""
    try:
        result = float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, result) if math.isfinite(result) else 0.0


def _events(session: Session, event_type: str, since: datetime,
            camera_id: Optional[int] = None, camera_ids=None):
    stmt = select(Event).where(Event.event_type == event_type, Event.timestamp >= since)
    if camera_id is not None:
        stmt = stmt.where(Event.camera_id == camera_id)
    elif camera_ids is not None:
        # Filtre par ENSEMBLE de caméras (scope agence). Ensemble vide = aucune
        # donnée (agence sans caméra) → in_([]) génère une condition fausse valide.
        stmt = stmt.where(Event.camera_id.in_(camera_ids))
    return session.exec(stmt.order_by(Event.timestamp)).all()


def _scope_camera_ids(session: Session, group_id: Optional[int], camera_id: Optional[int]):
    """Ensemble des camera_id ciblés par le filtre agence/caméra, ou None = toutes.
    `camera_id` prime sur `group_id`. Sert à SCOPER toutes les stats (pas seulement
    les files) : sans lui, les filtres du tableau de bord ne changeaient pas les
    chiffres d'affluence / occupation / incidents."""
    if camera_id is not None:
        return {camera_id}
    if group_id is not None:
        cams = session.exec(select(Camera).options(selectinload(Camera.groups))).all()
        return {c.id for c in cams if any(g.id == group_id for g in c.groups)}
    return None


def _filter_work_schedule(events, work_schedule_id: Optional[int]):
    """Filtre un historique par régime porté par l'événement.

    On ne relit pas l'affectation ACTUELLE de la zone/caméra : si elle change de
    groupe, ses anciens épisodes doivent rester attribués à l'ancien régime.
    """
    if work_schedule_id is None:
        return list(events)
    return [
        event for event in events
        if (event.meta or {}).get("schedule_id") == work_schedule_id
    ]


def _presence_event_is_reliable(event) -> bool:
    """Compatibilité qualité : marqueur v2, ou preuves de la bascule initiale.

    Le repli permet de ne pas perdre les deux premiers événements fiables créés
    juste avant la migration qui a matérialisé le statut dans leur JSON.
    """
    meta = event.meta or {}
    quality = meta.get("presence_data_quality")
    if quality == "archived":
        return False
    try:
        schema_version = int(meta.get("presence_schema_version") or 0)
    except (TypeError, ValueError):
        schema_version = 0
    if quality == "reliable" or schema_version >= 2:
        return True
    if event.event_type == EVENT_POST_VACANT:
        return isinstance(meta.get("decision"), dict)
    if event.event_type == EVENT_POST_ABSENCE:
        return bool(meta.get("resolution_reason"))
    return False


def _work_schedule_names(session: Session) -> dict:
    return {item.id: item.name for item in session.exec(select(WorkSchedule)).all()}


@router.get("/footfall")
@cached_endpoint("analytics:footfall", 120)
def footfall(
    days: int = Query(7, ge=1, le=90),
    camera_id: Optional[int] = None,
    group_id: Optional[int] = None,
    _user: User = Depends(require_viewer),
    session: Session = Depends(get_session),
):
    """Entrées / sorties / net par jour (depuis LINE_CROSSED, meta.direction)."""
    scope = _scope_camera_ids(session, group_id, camera_id)
    since_date = datetime.utcnow().date() - timedelta(days=days - 1)
    since_dt = datetime.combine(since_date, datetime.min.time())
    rows = _events(session, EVENT_LINE_CROSSED, since_dt, camera_ids=scope)

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
    prev_rows = [e for e in _events(session, EVENT_LINE_CROSSED, prev_since_dt, camera_ids=scope)
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
@cached_endpoint("analytics:occupancy", 30)
def occupancy(
    hours: int = Query(24, ge=1, le=168),
    zone_id: Optional[int] = None,
    camera_id: Optional[int] = None,
    group_id: Optional[int] = None,
    _user: User = Depends(require_viewer),
    session: Session = Depends(get_session),
):
    """Avec zone_id : série temporelle + moy/max/actuel. Sans : dernière
    occupation connue par zone (fenêtre `hours`). Scopé par agence/caméra."""
    scope = _scope_camera_ids(session, group_id, camera_id)
    since = datetime.utcnow() - timedelta(hours=hours)
    rows = _events(session, EVENT_ZONE_OCCUPANCY_CHANGED, since, camera_ids=scope)

    if zone_id is not None:
        pts = [
            {"t": e.timestamp.isoformat(), "count": (e.meta or {}).get("count", 0)}
            for e in rows if (e.meta or {}).get("zone_id") == zone_id
        ]
        counts = [p["count"] for p in pts]
        # Moyenne PONDÉRÉE PAR LA DURÉE : l'occupation est un ÉTAT, pas un évènement
        # — la moyenne brute des transitions serait fausse. On reconstruit la
        # fonction en escalier et on intègre.
        tw_num = tw_den = 0.0
        evs_sorted = sorted(
            ((e.timestamp, (e.meta or {}).get("count", 0)) for e in rows
             if (e.meta or {}).get("zone_id") == zone_id),
            key=lambda x: x[0],
        )
        if evs_sorted:
            cur_t, cur_c = evs_sorted[0]
            for t, c in evs_sorted[1:]:
                dur = (t - cur_t).total_seconds()
                if dur > 0:
                    tw_num += cur_c * dur; tw_den += dur
                cur_t, cur_c = t, c
            dur = (datetime.utcnow() - cur_t).total_seconds()
            if dur > 0:
                tw_num += cur_c * dur; tw_den += dur
        return {
            "zone_id": zone_id,
            "series": pts,
            "avg": round(tw_num / tw_den, 2) if tw_den else (counts[-1] if counts else 0),
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


@router.get("/summary")
@cached_endpoint("analytics:summary", 30)
def summary(
    camera_id: Optional[int] = None,
    group_id: Optional[int] = None,
    _user: User = Depends(require_viewer),
    session: Session = Depends(get_session),
):
    """KPIs du jour pour le dashboard opérationnel. Scopé par agence/caméra."""
    scope = _scope_camera_ids(session, group_id, camera_id)
    today = datetime.combine(datetime.utcnow().date(), datetime.min.time())
    since24 = datetime.utcnow() - timedelta(hours=24)

    lines = _events(session, EVENT_LINE_CROSSED, today, camera_ids=scope)
    entries = sum(1 for e in lines if (e.meta or {}).get("direction") == "in")
    exits = sum(1 for e in lines if (e.meta or {}).get("direction") == "out")
    crowd = len(_events(session, EVENT_CROWD_DETECTED, today, camera_ids=scope))

    occ = _events(session, EVENT_ZONE_OCCUPANCY_CHANGED, since24, camera_ids=scope)
    latest = {}
    for e in occ:
        zid = (e.meta or {}).get("zone_id")
        if zid is not None:
            latest[zid] = (e.meta or {}).get("count", 0)
    current_occupancy = sum(latest.values())

    dwell = _events(session, EVENT_ZONE_DWELL, today, camera_ids=scope)
    qids = {z.id for z in session.exec(select(Zone).where(Zone.kind == ZONE_QUEUE)).all()}
    qwaits = [
        (e.meta or {}).get("dwell_s") for e in dwell
        if (e.meta or {}).get("zone_id") in qids and (e.meta or {}).get("dwell_s") is not None
    ]

    # « Présents » fiable : l'occupation par zone est un compte INSTANTANÉ (jamais
    # négatif, sans dérive) → on la privilégie dès qu'au moins une zone d'occupation
    # rapporte. Sinon, repli sur le flux entrées−sorties du jour BORNÉ à 0 : ce solde
    # cumulé dérive (base minuit supposée vide + erreurs de comptage asymétriques) et
    # n'a aucun sens en négatif. `present_source` indique lequel est affiché.
    present_flow = max(0, entries - exits)
    present_now = current_occupancy if latest else present_flow
    return {
        "entries_today": entries,
        "exits_today": exits,
        "present_now_estimate": present_now,
        "present_source": "occupancy" if latest else "flow",
        "present_flow_estimate": present_flow,
        "current_occupancy": current_occupancy,
        "crowd_alerts_today": crowd,
        "avg_wait_s": round(sum(qwaits) / len(qwaits), 1) if qwaits else 0,
    }


@router.get("/by-camera")
@cached_endpoint("analytics:by-camera", 120)
def by_camera(
    days: int = Query(7, ge=1, le=90),
    camera_id: Optional[int] = None,
    group_id: Optional[int] = None,
    _user: User = Depends(require_viewer),
    session: Session = Depends(get_session),
):
    """Répartition SPATIALE de l'affluence : entrées/sorties + occupation courante
    par caméra, et agrégat par site (groupe). Répond à « quelle agence / caméra
    est la plus fréquentée ? ». Scopé par agence/caméra."""
    scope = _scope_camera_ids(session, group_id, camera_id)
    since_date = datetime.utcnow().date() - timedelta(days=days - 1)
    since_dt = datetime.combine(since_date, datetime.min.time())
    lines = _events(session, EVENT_LINE_CROSSED, since_dt, camera_ids=scope)
    occ = _events(session, EVENT_ZONE_OCCUPANCY_CHANGED, since_dt, camera_ids=scope)

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
@cached_endpoint("analytics:incidents", 120)
def incidents(
    days: int = Query(7, ge=1, le=90),
    camera_id: Optional[int] = None,
    group_id: Optional[int] = None,
    _user: User = Depends(require_viewer),
    session: Session = Depends(get_session),
):
    """Analyse SÉCURITÉ : attroupements détectés (CROWD_DETECTED) + alertes du
    centre d'alertes — timeline journalière, répartition par sévérité / type /
    caméra, et taux de résolution du workflow. Scopé par agence/caméra."""
    scope = _scope_camera_ids(session, group_id, camera_id)
    since_date = datetime.utcnow().date() - timedelta(days=days - 1)
    since_dt = datetime.combine(since_date, datetime.min.time())
    crowd = _events(session, EVENT_CROWD_DETECTED, since_dt, camera_ids=scope)
    astmt = select(Alert).where(Alert.created_at >= since_dt)
    if scope is not None:
        astmt = astmt.where(Alert.camera_id.in_(scope))
    alerts = session.exec(astmt).all()

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


@router.get("/post-absence")
@cached_endpoint("analytics:post-absence", 60)
def post_absence(
    days: int = Query(30, ge=1, le=180),
    camera_id: Optional[int] = None,
    group_id: Optional[int] = None,
    work_schedule_id: Optional[int] = Query(None, ge=1),
    _user: User = Depends(require_viewer),
    session: Session = Depends(get_session),
):
    """Absences aux postes : signal temps réel + épisodes clôturés.

    ``POST_VACANT`` répond à « quels postes sont vacants maintenant ? ».
    ``POST_ABSENCE`` porte la durée finale et alimente les cumuls, moyennes et
    classements. Les deux sont rapprochés par ``meta.episode_id``.
    """
    scope = _scope_camera_ids(session, group_id, camera_id)
    since_date = datetime.utcnow().date() - timedelta(days=days - 1)
    since_dt = datetime.combine(since_date, datetime.min.time())
    raw_vacant = _filter_work_schedule(
        _events(session, EVENT_POST_VACANT, since_dt, camera_ids=scope),
        work_schedule_id,
    )
    raw_closed = _filter_work_schedule(
        _events(session, EVENT_POST_ABSENCE, since_dt, camera_ids=scope),
        work_schedule_id,
    )
    vacant = [event for event in raw_vacant if _presence_event_is_reliable(event)]
    closed = [event for event in raw_closed if _presence_event_is_reliable(event)]
    reliable_events = vacant + closed
    reliable_since = min(
        (event.timestamp for event in reliable_events), default=None
    )

    def episode_id(event):
        return (event.meta or {}).get("episode_id")

    closed_ids = {episode_id(e) for e in closed if episode_id(e)}
    current = [e for e in vacant if episode_id(e) and episode_id(e) not in closed_ids]
    # Compatibilité avec d'éventuels anciens signaux sans episode_id : ils restent
    # comptés dans le volume de signaux, mais ne sont pas déclarés « encore ouverts ».

    per_day = defaultdict(lambda: {"episodes": 0, "absence_s": 0.0})
    per_zone = defaultdict(lambda: {
        "episodes": 0, "total_absence_s": 0.0, "max_absence_s": 0.0,
        "zone_name": None, "camera_id": None, "schedule_id": None,
        "schedule_name": None,
    })
    per_schedule = defaultdict(lambda: {
        "episodes": 0, "total_s": 0.0, "max_s": 0.0, "name": None,
    })
    durations = []
    for event in closed:
        meta = event.meta or {}
        duration = _seconds(meta.get("absence_s"))
        durations.append(duration)
        day = event.timestamp.date().isoformat()
        per_day[day]["episodes"] += 1
        per_day[day]["absence_s"] += duration
        zid = meta.get("zone_id")
        sid = meta.get("schedule_id")
        if sid is not None:
            schedule_row = per_schedule[sid]
            schedule_row["episodes"] += 1
            schedule_row["total_s"] += duration
            schedule_row["max_s"] = max(schedule_row["max_s"], duration)
            schedule_row["name"] = meta.get("schedule_name") or schedule_row["name"]
        if zid is not None:
            row = per_zone[(zid, sid)]
            row["episodes"] += 1
            row["total_absence_s"] += duration
            row["max_absence_s"] = max(row["max_absence_s"], duration)
            row["zone_name"] = meta.get("zone_name") or row["zone_name"]
            row["camera_id"] = event.camera_id
            row["schedule_id"] = sid
            row["schedule_name"] = meta.get("schedule_name") or row["schedule_name"]

    cameras = session.exec(select(Camera).options(selectinload(Camera.groups))).all()
    camera_meta = {
        c.id: {
            "camera_name": c.cam_name,
            "site": c.groups[0].name if c.groups else None,
        }
        for c in cameras
    }
    zones = []
    for (zid, _sid), row in per_zone.items():
        meta = camera_meta.get(row["camera_id"], {})
        episodes = row["episodes"]
        zones.append({
            "zone_id": zid,
            "zone_name": row["zone_name"] or f"Poste {zid}",
            "camera_id": row["camera_id"],
            "camera_name": meta.get("camera_name") or f"Caméra {row['camera_id']}",
            "site": meta.get("site"),
            "work_schedule_id": row["schedule_id"],
            "work_schedule_name": row["schedule_name"],
            "episodes": episodes,
            "total_absence_s": round(row["total_absence_s"], 1),
            "avg_absence_s": round(row["total_absence_s"] / episodes, 1) if episodes else 0,
            "max_absence_s": round(row["max_absence_s"], 1),
        })
    zones.sort(key=lambda row: row["total_absence_s"], reverse=True)

    current_posts = []
    for event in current:
        meta = event.meta or {}
        cam = camera_meta.get(event.camera_id, {})
        vacant_s = _seconds(meta.get("vacant_s"))
        current_posts.append({
            "episode_id": meta.get("episode_id"),
            "zone_id": meta.get("zone_id"),
            "zone_name": meta.get("zone_name") or "Poste",
            "camera_id": event.camera_id,
            "camera_name": cam.get("camera_name") or f"Caméra {event.camera_id}",
            "site": cam.get("site"),
            "work_schedule_id": meta.get("schedule_id"),
            "work_schedule_name": meta.get("schedule_name"),
            # POST_VACANT est envoyé APRÈS la tolérance : reconstruire le vrai
            # début, sans quoi l'UI le décalerait de 5/10/30 minutes.
            "vacant_since": (event.timestamp - timedelta(seconds=vacant_s)).isoformat(),
            "vacant_s_at_signal": vacant_s,
        })

    series = []
    for i in range(days):
        day = (since_date + timedelta(days=i)).isoformat()
        row = per_day[day]
        series.append({
            "date": day,
            "episodes": row["episodes"],
            "absence_s": round(row["absence_s"], 1),
            "absence_minutes": round(row["absence_s"] / 60.0, 1),
        })

    total_s = sum(durations)
    schedule_names = _work_schedule_names(session)
    open_by_schedule = defaultdict(int)
    for event in current:
        sid = (event.meta or {}).get("schedule_id")
        if sid is not None:
            open_by_schedule[sid] += 1
    schedule_rows = []
    for sid in set(per_schedule) | set(open_by_schedule):
        row = per_schedule[sid]
        episodes = row["episodes"]
        schedule_rows.append({
            "work_schedule_id": sid,
            "work_schedule_name": schedule_names.get(sid) or row["name"] or f"Groupe {sid}",
            "episodes": episodes,
            "current_vacant": open_by_schedule[sid],
            "total_absence_s": round(row["total_s"], 1),
            "avg_absence_s": round(row["total_s"] / episodes, 1) if episodes else 0,
            "max_absence_s": round(row["max_s"], 1),
        })
    schedule_rows.sort(key=lambda row: row["total_absence_s"], reverse=True)
    return {
        "days": days,
        "vacant_signals": len(vacant),
        "closed_episodes": len(closed),
        "current_vacant": len(current_posts),
        "affected_posts": len(per_zone),
        "total_absence_s": round(total_s, 1),
        "avg_absence_s": round(total_s / len(durations), 1) if durations else 0,
        "max_absence_s": round(max(durations), 1) if durations else 0,
        "series": series,
        "zones": zones,
        "schedules": schedule_rows,
        "current_posts": current_posts,
        "data_quality": {
            "scope": "reliable_only",
            "reliable_since": reliable_since.isoformat() if reliable_since else None,
            "archived_vacant_signals": len(raw_vacant) - len(vacant),
            "archived_closed_episodes": len(raw_closed) - len(closed),
            "archived_total": (
                len(raw_vacant) + len(raw_closed) - len(vacant) - len(closed)
            ),
        },
    }


@router.get("/staffing")
@cached_endpoint("analytics:staffing", 60)
def staffing(
    days: int = Query(30, ge=1, le=180),
    camera_id: Optional[int] = None,
    group_id: Optional[int] = None,
    work_schedule_id: Optional[int] = Query(None, ge=1),
    _user: User = Depends(require_viewer),
    session: Session = Depends(get_session),
):
    """Sous-effectif caméra : signaux ouverts, durées et classement.

    Le Core compte l'union des personnes confirmées dans les zones `presence` :
    un client hors de ces zones n'augmente donc pas artificiellement l'effectif.
    """
    scope = _scope_camera_ids(session, group_id, camera_id)
    since_date = datetime.utcnow().date() - timedelta(days=days - 1)
    since_dt = datetime.combine(since_date, datetime.min.time())
    low_events = _filter_work_schedule(
        _events(session, EVENT_STAFFING_LOW, since_dt, camera_ids=scope),
        work_schedule_id,
    )
    recovered = _filter_work_schedule(
        _events(session, EVENT_STAFFING_RECOVERED, since_dt, camera_ids=scope),
        work_schedule_id,
    )

    def episode_id(event):
        return (event.meta or {}).get("episode_id")

    recovered_ids = {episode_id(event) for event in recovered if episode_id(event)}
    current = [
        event for event in low_events
        if episode_id(event) and episode_id(event) not in recovered_ids
    ]

    cameras = session.exec(select(Camera).options(selectinload(Camera.groups))).all()
    camera_meta = {
        camera.id: {
            "camera_name": camera.cam_name,
            "site": camera.groups[0].name if camera.groups else None,
            "minimum": camera.staffing_min_agents,
            "maximum": camera.staffing_max_agents,
            "configured": (
                camera.staffing_min_agents is not None
                and camera.staffing_max_agents is not None
            ),
            "work_schedule_id": camera.staffing_work_schedule_id,
        }
        for camera in cameras
        if scope is None or camera.id in scope
    }

    per_day = defaultdict(lambda: {"episodes": 0, "shortage_s": 0.0})
    per_camera = defaultdict(
        lambda: {"episodes": 0, "total_shortage_s": 0.0, "max_shortage_s": 0.0}
    )
    per_schedule = defaultdict(lambda: {
        "episodes": 0, "total_s": 0.0, "max_s": 0.0, "name": None,
    })
    durations = []
    for event in recovered:
        event_meta = event.meta or {}
        duration = _seconds(event_meta.get("shortage_s"))
        durations.append(duration)
        day = event.timestamp.date().isoformat()
        per_day[day]["episodes"] += 1
        per_day[day]["shortage_s"] += duration
        sid = event_meta.get("schedule_id")
        row = per_camera[(event.camera_id, sid)]
        row["episodes"] += 1
        row["total_shortage_s"] += duration
        row["max_shortage_s"] = max(row["max_shortage_s"], duration)
        if sid is not None:
            schedule_row = per_schedule[sid]
            schedule_row["episodes"] += 1
            schedule_row["total_s"] += duration
            schedule_row["max_s"] = max(schedule_row["max_s"], duration)
            schedule_row["name"] = event_meta.get("schedule_name") or schedule_row["name"]

    schedule_names = _work_schedule_names(session)
    camera_rows = []
    for (cid, sid), row in per_camera.items():
        meta = camera_meta.get(cid, {})
        episodes = row["episodes"]
        camera_rows.append({
            "camera_id": cid,
            "camera_name": meta.get("camera_name") or f"Caméra {cid}",
            "site": meta.get("site"),
            "work_schedule_id": sid,
            "work_schedule_name": schedule_names.get(sid) if sid is not None else None,
            "minimum": meta.get("minimum"),
            "maximum": meta.get("maximum"),
            "episodes": episodes,
            "total_shortage_s": round(row["total_shortage_s"], 1),
            "avg_shortage_s": round(row["total_shortage_s"] / episodes, 1)
            if episodes else 0,
            "max_shortage_s": round(row["max_shortage_s"], 1),
        })
    camera_rows.sort(key=lambda row: row["total_shortage_s"], reverse=True)

    current_cameras = []
    for event in current:
        event_meta = event.meta or {}
        meta = camera_meta.get(event.camera_id, {})
        low_s = _seconds(event_meta.get("low_s"))
        current_cameras.append({
            "episode_id": event_meta.get("episode_id"),
            "camera_id": event.camera_id,
            "camera_name": meta.get("camera_name") or f"Caméra {event.camera_id}",
            "site": meta.get("site"),
            "work_schedule_id": event_meta.get("schedule_id"),
            "work_schedule_name": event_meta.get("schedule_name"),
            "count": event_meta.get("count"),
            "minimum": event_meta.get("minimum"),
            "maximum": event_meta.get("maximum"),
            "missing": event_meta.get("missing"),
            "low_since": (event.timestamp - timedelta(seconds=low_s)).isoformat(),
        })

    series = []
    for offset in range(days):
        day = (since_date + timedelta(days=offset)).isoformat()
        row = per_day[day]
        series.append({
            "date": day,
            "episodes": row["episodes"],
            "shortage_s": round(row["shortage_s"], 1),
            "shortage_minutes": round(row["shortage_s"] / 60.0, 1),
        })

    total_s = sum(durations)
    open_by_schedule = defaultdict(int)
    for event in current:
        sid = (event.meta or {}).get("schedule_id")
        if sid is not None:
            open_by_schedule[sid] += 1
    schedule_rows = []
    for sid in set(per_schedule) | set(open_by_schedule):
        row = per_schedule[sid]
        episodes = row["episodes"]
        schedule_rows.append({
            "work_schedule_id": sid,
            "work_schedule_name": schedule_names.get(sid) or row["name"] or f"Groupe {sid}",
            "episodes": episodes,
            "current_shortages": open_by_schedule[sid],
            "total_shortage_s": round(row["total_s"], 1),
            "avg_shortage_s": round(row["total_s"] / episodes, 1) if episodes else 0,
            "max_shortage_s": round(row["max_s"], 1),
        })
    schedule_rows.sort(key=lambda row: row["total_shortage_s"], reverse=True)
    return {
        "days": days,
        "configured_cameras": sum(
            1 for meta in camera_meta.values()
            if meta["configured"] and (
                work_schedule_id is None
                or meta["work_schedule_id"] == work_schedule_id
            )
        ),
        "low_signals": len(low_events),
        "closed_episodes": len(recovered),
        "current_shortages": len(current_cameras),
        "affected_cameras": len(per_camera),
        "total_shortage_s": round(total_s, 1),
        "avg_shortage_s": round(total_s / len(durations), 1) if durations else 0,
        "max_shortage_s": round(max(durations), 1) if durations else 0,
        "series": series,
        "cameras": camera_rows,
        "schedules": schedule_rows,
        "current_cameras": current_cameras,
    }


# ─────────────────────────────────────────────
# ANALYSE DES FILES (queue zones) — affluence basée occupation + performance
# ─────────────────────────────────────────────
def _accumulate_occupancy(evs, since, now, PS_H, S_H, PS_WH, S_WH, PS_DH, S_DH):
    """Intègre la fonction en escalier d'occupation d'UNE zone (transitions
    (timestamp, count)) en person-secondes/secondes, PONDÉRÉES PAR LA DURÉE, dans
    des seaux par heure, par (jour_semaine, heure) et par (date, heure). Chaque
    segment est découpé aux frontières horaires → moyenne temporelle EXACTE."""
    if not evs:
        return
    cur_t = max(since, evs[0][0])
    cur_c = evs[0][1]
    segments = []
    for t, c in evs[1:]:
        if t <= cur_t:
            cur_c = c
            continue
        segments.append((cur_t, t, cur_c))
        cur_t, cur_c = t, c
    segments.append((cur_t, now, cur_c))
    for a, b, c in segments:
        t = a
        while t < b:
            hour_end = t.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
            seg_end = min(b, hour_end)
            dur = (seg_end - t).total_seconds()
            if dur > 0:
                h, wd, d = t.hour, t.weekday(), t.date()
                PS_H[h] += c * dur; S_H[h] += dur
                PS_WH[(wd, h)] += c * dur; S_WH[(wd, h)] += dur
                PS_DH[(d, h)] += c * dur; S_DH[(d, h)] += dur
            t = seg_end


def _target_queue_zones(session, group_id, camera_id, zone_id):
    """Zones de type 'queue' ciblées → {zone_id: {name, camera_id, site, threshold}}."""
    stmt = select(Zone).where(Zone.kind == ZONE_QUEUE)
    if zone_id is not None:
        stmt = stmt.where(Zone.id == zone_id)
    if camera_id is not None:
        stmt = stmt.where(Zone.camera_id == camera_id)
    zones = session.exec(stmt).all()
    cam_ids = {z.camera_id for z in zones}
    cams = session.exec(
        select(Camera).options(selectinload(Camera.groups)).where(Camera.id.in_(cam_ids))
    ).all() if cam_ids else []
    site = {c.id: (c.groups[0].name if c.groups else None) for c in cams}
    gids = {c.id: [g.id for g in c.groups] for c in cams}
    if group_id is not None:
        zones = [z for z in zones if group_id in gids.get(z.camera_id, [])]
    return {z.id: {"name": z.name, "camera_id": z.camera_id,
                   "site": site.get(z.camera_id), "threshold": z.threshold} for z in zones}


@router.get("/queue-affluence")
@cached_endpoint("analytics:queue-affluence", 120)
def queue_affluence(
    days: int = Query(30, ge=1, le=180),
    group_id: Optional[int] = None,
    camera_id: Optional[int] = None,
    zone_id: Optional[int] = None,
    top: int = Query(8, ge=1, le=50),
    _user: User = Depends(require_viewer),
    session: Session = Depends(get_session),
):
    """Affluence basée sur l'OCCUPATION DES FILES (zones 'queue'), pondérée par la
    durée : profil horaire, heatmap jour×heure, heure de pointe/creux et TOP des
    moments les plus chargés. Filtres agence/caméra/file."""
    now = datetime.utcnow()
    since = now - timedelta(days=days)
    zmeta = _target_queue_zones(session, group_id, camera_id, zone_id)
    zids = set(zmeta)
    if not zids:
        return {"days": days, "has_queues": False, "queues": 0, "hourly": [],
                "heatmap": [], "heatmap_max": 0, "peak_hour": None, "quietest_hour": None,
                "busiest_periods": []}

    occ = _events(session, EVENT_ZONE_OCCUPANCY_CHANGED, since)
    by_zone = defaultdict(list)
    for e in occ:
        zid = (e.meta or {}).get("zone_id")
        if zid in zids:
            by_zone[zid].append((e.timestamp, (e.meta or {}).get("count", 0)))

    PS_H, S_H = defaultdict(float), defaultdict(float)
    PS_WH, S_WH = defaultdict(float), defaultdict(float)
    PS_DH, S_DH = defaultdict(float), defaultdict(float)
    for zid, evs in by_zone.items():
        evs.sort(key=lambda x: x[0])
        _accumulate_occupancy(evs, since, now, PS_H, S_H, PS_WH, S_WH, PS_DH, S_DH)

    HOURS = list(range(24))
    avg_h = {h: (PS_H[h] / S_H[h] if S_H[h] else 0.0) for h in HOURS}
    hourly = [{"hour": h, "avg_occupancy": round(avg_h[h], 2)} for h in HOURS]
    heatmap = [[round(PS_WH[(wd, h)] / S_WH[(wd, h)], 2) if S_WH[(wd, h)] else 0.0 for h in HOURS] for wd in range(7)]
    heatmap_max = max((max(row) for row in heatmap), default=0)

    has_data = any(S_H.values())
    peak_hour = max(HOURS, key=lambda h: avg_h[h]) if has_data else None
    biz = [h for h in HOURS if 6 <= h <= 22]
    quietest_hour = min(biz, key=lambda h: avg_h[h]) if has_data else None

    periods = [{"date": d.isoformat(), "hour": h, "avg_occupancy": round(PS_DH[(d, h)] / S_DH[(d, h)], 2)}
               for (d, h) in S_DH if S_DH[(d, h)] > 0]
    periods.sort(key=lambda p: -p["avg_occupancy"])

    return {
        "days": days, "has_queues": True, "queues": len(zids),
        "hourly": hourly, "heatmap": heatmap, "heatmap_max": round(heatmap_max, 2),
        "peak_hour": peak_hour, "peak_avg_occupancy": round(avg_h[peak_hour], 2) if peak_hour is not None else 0,
        "quietest_hour": quietest_hour,
        "busiest_periods": periods[:top],
    }


@router.get("/queue-performance")
@cached_endpoint("analytics:queue-performance", 30)
def queue_performance(
    days: int = Query(7, ge=1, le=90),
    group_id: Optional[int] = None,
    camera_id: Optional[int] = None,
    wait_threshold_s: int = Query(300, ge=10, le=7200),
    _user: User = Depends(require_viewer),
    session: Session = Depends(get_session),
):
    """Performance des files : longueur, attente MOYENNE + P90 + max, % au-dessus du
    seuil (SLA), par file ; et CLASSEMENT DES AGENCES par temps d'attente moyen."""
    now = datetime.utcnow()
    since = now - timedelta(days=days)
    zmeta = _target_queue_zones(session, group_id, camera_id, None)
    zids = set(zmeta)
    if not zids:
        return {"days": days, "wait_threshold_s": wait_threshold_s, "queues": [], "agencies": []}

    dwell = _events(session, EVENT_ZONE_DWELL, since)
    occ = _events(session, EVENT_ZONE_OCCUPANCY_CHANGED, since)
    waits = defaultdict(list)
    for e in dwell:
        zid = (e.meta or {}).get("zone_id")
        w = (e.meta or {}).get("dwell_s")
        if zid in zids and w is not None:
            waits[zid].append(w)
    last_len = {}
    for e in occ:
        zid = (e.meta or {}).get("zone_id")
        if zid in zids:
            last_len[zid] = (e.meta or {}).get("count", 0)

    def _p90(vals):
        if not vals:
            return 0
        s = sorted(vals)
        return round(s[min(len(s) - 1, int(0.9 * len(s)))], 1)

    def _avg(vals):
        return round(sum(vals) / len(vals), 1) if vals else 0

    queues = []
    for zid, zm in zmeta.items():
        ws = waits.get(zid, [])
        over = sum(1 for w in ws if w > wait_threshold_s)
        queues.append({
            "zone_id": zid, "name": zm["name"], "site": zm["site"], "camera_id": zm["camera_id"],
            "length": last_len.get(zid, 0), "wait_avg_s": _avg(ws), "wait_p90_s": _p90(ws),
            "wait_max_s": round(max(ws), 1) if ws else 0, "samples": len(ws),
            "over_threshold_pct": round(100 * over / len(ws)) if ws else None,
        })
    queues.sort(key=lambda q: -q["wait_avg_s"])

    by_site = defaultdict(list)
    for zid, zm in zmeta.items():
        for w in waits.get(zid, []):
            by_site[zm["site"] or "Sans site"].append(w)
    agencies = [{"site": s, "wait_avg_s": _avg(v), "wait_p90_s": _p90(v),
                 "over_threshold_pct": round(100 * sum(1 for w in v if w > wait_threshold_s) / len(v)),
                 "samples": len(v)} for s, v in by_site.items() if v]
    agencies.sort(key=lambda a: -a["wait_avg_s"])

    return {"days": days, "wait_threshold_s": wait_threshold_s, "queues": queues, "agencies": agencies}


@router.get("/insights")
@cached_endpoint("analytics:insights", 120)
def insights(
    days: int = Query(30, ge=7, le=180),
    camera_id: Optional[int] = None,
    group_id: Optional[int] = None,
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
    scope = _scope_camera_ids(session, group_id, camera_id)
    now = datetime.utcnow()
    since_date = now.date() - timedelta(days=days - 1)
    since_dt = datetime.combine(since_date, datetime.min.time())
    lines = _events(session, EVENT_LINE_CROSSED, since_dt, camera_ids=scope)

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


@router.get("/cockpit")
@cached_endpoint("analytics:cockpit", 300)
def cockpit_overview(
    group_id: Optional[int] = None,
    camera_id: Optional[int] = None,
    _user: User = Depends(require_viewer),
    session: Session = Depends(get_session),
):
    """Vue agrégée du Cockpit en UNE requête : résumé du jour, occupation des
    zones, performance des files et disponibilité caméras — les 4 blocs les plus
    coûteux, scopés agence/caméra. Remplace 4 appels séparés répétés toutes les 8 s.
    Chaque bloc RÉUTILISE le cache de son sous-endpoint (aucun recalcul redondant :
    le Cockpit et les pages qui appellent ces endpoints directement partagent le
    même cache).

    Cache PROPRE de 5 min (300 s) au-dessus de ces caches : le Cockpit est un écran
    de synthèse quotidienne, pas un mur temps réel (celui-ci passe par Socket.IO).
    La base n'est donc plus sollicitée qu'une fois par 5 min pour cet écran, quel
    que soit le nombre d'opérateurs connectés — contre ~2 recalculs par minute
    auparavant (TTL de 30 s des sous-endpoints). Contrepartie assumée : les chiffres
    peuvent avoir jusqu'à 5 min de retard ICI. Les autres pages qui appellent ces
    mêmes sous-endpoints gardent, elles, leur fraîcheur de 30 s."""
    return {
        "summary": summary(camera_id=camera_id, group_id=group_id, session=session, _user=_user),
        "occupancy": occupancy(hours=24, zone_id=None, camera_id=camera_id, group_id=group_id,
                               session=session, _user=_user),
        "queue_performance": queue_performance(
            days=1, group_id=group_id, camera_id=camera_id,
            wait_threshold_s=300, session=session, _user=_user),
        "camera_status": camera_status_stats(
            days=1, group_id=group_id, camera_id=camera_id,
            session=session, _user=_user),
    }

# app/routes/alerts_routes.py
"""
Centre d'alertes (hits blacklist).

Workflow : new → acknowledged → resolved (acquittement / résolution).

⚠️ Notifications (email/webhook) : envoyées UNIQUEMENT via POST /{id}/notify,
c'est-à-dire sur action explicite d'un utilisateur. Aucun envoi automatique.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select, func
from sqlalchemy.orm import selectinload
from datetime import datetime
from typing import Optional
from pydantic import BaseModel
import logging

from app.database import get_session
from app.models.alerts import Alert, ALERT_NEW, ALERT_ACKNOWLEDGED, ALERT_RESOLVED
from app.models.cameras import Camera
from app.middleware.auth_middleware import require_viewer, require_user
from app.services.notification_service import (
    send_email, send_webhook, email_configured, webhook_configured, snapshot_local_path,
    compose_alert_email,
)

router = APIRouter()
logger = logging.getLogger(__name__)


class NotifyRequest(BaseModel):
    channel: str = "email"     # "email" | "webhook" | "both"
    to: Optional[str] = None   # surcharge facultative du destinataire email


class ResolveAllRequest(BaseModel):
    # None / "all" → toutes les non-résolues ; "new" | "acknowledged" → ce statut seul.
    status: Optional[str] = None


def _scope_camera_ids(session: Session, group_id: Optional[int], camera_id: Optional[int]):
    """camera_id ciblés par le filtre agence/caméra, ou None = toutes.
    `camera_id` prime sur `group_id`."""
    if camera_id is not None:
        return {camera_id}
    if group_id is not None:
        cams = session.exec(select(Camera).options(selectinload(Camera.groups))).all()
        return {c.id for c in cams if any(g.id == group_id for g in c.groups)}
    return None


def _serialize(a: Alert, cam_name: Optional[str]) -> dict:
    return {
        "id": a.id, "kind": a.kind, "severity": a.severity, "label": a.label, "reason": a.reason,
        "camera_id": a.camera_id, "camera_name": cam_name,
        "snapshot_url": a.snapshot_url, "status": a.status,
        "acknowledged_at": a.acknowledged_at, "acknowledged_by": a.acknowledged_by,
        "notified_at": a.notified_at, "notified_channel": a.notified_channel,
        "notify_attempts": a.notify_attempts,
        "notify_last_error": a.notify_last_error,
        "notify_next_retry_at": a.notify_next_retry_at,
        "notify_requested_channels": a.notify_requested_channels,
        "created_at": a.created_at,
    }


@router.get("/")
def list_alerts(
    status: Optional[str] = None,
    group_id: Optional[int] = None,
    camera_id: Optional[int] = None,
    skip: int = 0,
    limit: int = Query(200, ge=1, le=500),
    _current_user=Depends(require_viewer),
    session: Session = Depends(get_session),
):
    """Liste paginée, scopée agence/caméra. Pour un COMPTE, utiliser /stats :
    la longueur de cette liste vaut la taille de page, pas le total."""
    stmt = select(Alert)
    if status and status not in ("all", "tous"):
        stmt = stmt.where(Alert.status == status)
    scope = _scope_camera_ids(session, group_id, camera_id)
    if scope is not None:
        stmt = stmt.where(Alert.camera_id.in_(scope))
    stmt = stmt.order_by(Alert.id.desc()).offset(skip).limit(limit)
    alerts = session.exec(stmt).all()

    cam_ids = {a.camera_id for a in alerts if a.camera_id}
    cam_map = {}
    if cam_ids:
        cams = session.exec(select(Camera).where(Camera.id.in_(cam_ids))).all()
        cam_map = {c.id: c.cam_name for c in cams}

    return [_serialize(a, cam_map.get(a.camera_id)) for a in alerts]


@router.get("/stats")
def alert_stats(
    group_id: Optional[int] = None,
    camera_id: Optional[int] = None,
    _current_user=Depends(require_viewer),
    session: Session = Depends(get_session),
):
    """Compteurs par statut, scopés agence/caméra. Agrégé en base (GROUP BY) :
    la table dépasse le millier de lignes et l'endpoint est appelé en boucle."""
    scope = _scope_camera_ids(session, group_id, camera_id)
    stmt = select(Alert.status, func.count()).group_by(Alert.status)
    if scope is not None:
        stmt = stmt.where(Alert.camera_id.in_(scope))
    by_status = {status: count for status, count in session.exec(stmt).all()}
    return {
        "total": sum(by_status.values()),
        "new": by_status.get(ALERT_NEW, 0),
        "acknowledged": by_status.get(ALERT_ACKNOWLEDGED, 0),
        "resolved": by_status.get(ALERT_RESOLVED, 0),
        "notifications": {"email": email_configured(), "webhook": webhook_configured()},
    }


@router.post("/resolve-all")
def resolve_all_alerts(
    req: Optional[ResolveAllRequest] = None,
    _current_user=Depends(require_user),
    session: Session = Depends(get_session),
):
    """Action GROUPÉE : marque comme RÉSOLUES toutes les alertes non résolues.
    Avec `status` (new|acknowledged) : ne traite que ce statut ; sinon tous les
    non-résolus. Renvoie le nombre d'alertes effectivement résolues.

    Déclaré AVANT les routes /{alert_id}/… : chemin fixe à un segment, aucune
    collision (les autres exigent un id entier + un second segment)."""
    stmt = select(Alert).where(Alert.status != ALERT_RESOLVED)
    if req and req.status and req.status not in ("all", "tous"):
        stmt = stmt.where(Alert.status == req.status)
    alerts = session.exec(stmt).all()
    for a in alerts:
        a.status = ALERT_RESOLVED
        session.add(a)
    if alerts:
        session.commit()
    return {"resolved": len(alerts)}


@router.post("/{alert_id}/acknowledge")
def acknowledge_alert(
    alert_id: int,
    current_user=Depends(require_user),
    session: Session = Depends(get_session),
):
    alert = session.get(Alert, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alerte non trouvée.")
    alert.status = ALERT_ACKNOWLEDGED
    alert.acknowledged_at = datetime.utcnow()
    alert.acknowledged_by = getattr(current_user, "id", None)
    session.add(alert)
    session.commit()
    session.refresh(alert)
    return {"id": alert.id, "status": alert.status}


@router.post("/{alert_id}/resolve")
def resolve_alert(
    alert_id: int,
    _current_user=Depends(require_user),
    session: Session = Depends(get_session),
):
    alert = session.get(Alert, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alerte non trouvée.")
    alert.status = ALERT_RESOLVED
    session.add(alert)
    session.commit()
    session.refresh(alert)
    return {"id": alert.id, "status": alert.status}


@router.post("/{alert_id}/notify")
def notify_alert(
    alert_id: int,
    req: NotifyRequest,
    _current_user=Depends(require_user),
    session: Session = Depends(get_session),
):
    """Envoi MANUEL d'une notification (email/webhook) pour cette alerte.

    Déclenché par un utilisateur — jamais automatiquement. Renvoie le détail
    par canal ; 502 si tous les canaux demandés échouent (mal configuré, réseau)."""
    alert = session.get(Alert, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alerte non trouvée.")

    snap_path = snapshot_local_path(alert.snapshot_url)
    subject, body = compose_alert_email(alert)
    payload = {
        "source": "osirion", "alert_id": alert.id, "kind": alert.kind,
        "label": alert.label, "reason": alert.reason, "camera_id": alert.camera_id,
        "created_at": str(alert.created_at), "status": alert.status,
    }

    ch = (req.channel or "email").lower()
    do_email = ch in ("email", "both")
    do_webhook = ch in ("webhook", "both")

    results, ok_channels = [], []
    if do_email:
        ok, msg = send_email(subject, body, to=req.to, attachment_path=snap_path)
        results.append({"channel": "email", "ok": ok, "message": msg})
        if ok:
            ok_channels.append("email")
    if do_webhook:
        ok, msg = send_webhook(payload)
        results.append({"channel": "webhook", "ok": ok, "message": msg})
        if ok:
            ok_channels.append("webhook")

    if not results:
        raise HTTPException(status_code=400, detail="Canal inconnu (email | webhook | both).")

    if ok_channels:
        alert.notified_at = datetime.utcnow()
        alert.notified_channel = ",".join(ok_channels)
        session.add(alert)
        session.commit()
        return {"id": alert.id, "notified_channel": alert.notified_channel, "results": results}

    # Aucun canal n'a abouti.
    raise HTTPException(status_code=502, detail={"message": "Échec de la notification.", "results": results})

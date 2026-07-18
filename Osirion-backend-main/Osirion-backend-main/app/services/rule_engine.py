# app/services/rule_engine.py
"""
Moteur de règles — évalué À L'INGESTION d'un événement (POST /events/add).

Pour chaque règle active dont le `trigger` == event_type : vérifie la zone, la
plage horaire armée et les conditions (contre event.meta) ; si tout matche, crée
une Alerte et, si la règle le demande, envoie les notifications (email/webhook).

Best-effort : ne lève JAMAIS vers l'appelant (l'enregistrement d'un événement ne
doit pas échouer à cause d'une règle).
"""
import logging
from datetime import datetime, time, timedelta

from sqlmodel import Session, select

from app.models.rules import Rule
from app.models.alerts import Alert
from app.models.events import Event
from app.services.notification_service import send_email, send_webhook
from app.config import settings

logger = logging.getLogger(__name__)


def _parse_hhmm(s):
    try:
        h, m = str(s).split(":")
        return time(int(h), int(m))
    except Exception:
        return None


def _schedule_armed(schedule, now: datetime) -> bool:
    """Vrai si `now` tombe dans la fenêtre armée. None → toujours armé.
    Gère les fenêtres à cheval sur minuit (from > to, ex. 22:00 → 06:00)."""
    if not schedule:
        return True
    days = schedule.get("days")
    if days is not None and now.weekday() not in days:   # weekday(): 0 = lundi
        return False
    f = _parse_hhmm(schedule.get("from"))
    t = _parse_hhmm(schedule.get("to"))
    if f is None or t is None:
        return True
    cur = now.time()
    if f <= t:
        return f <= cur <= t
    return cur >= f or cur <= t   # fenêtre de nuit (chevauche minuit)


def _conditions_met(cond, event: Event) -> bool:
    cond = cond or {}
    meta = event.meta or {}
    if "min_count" in cond and (meta.get("count") or 0) < cond["min_count"]:
        return False
    if "min_wait_s" in cond and (meta.get("dwell_s") or 0) < cond["min_wait_s"]:
        return False
    if "direction" in cond and meta.get("direction") != cond["direction"]:
        return False
    return True


def _label(rule: Rule, event: Event) -> str:
    meta = event.meta or {}
    ctx = meta.get("zone_name") or meta.get("line_name") or ""
    extra = []
    if meta.get("count") is not None:
        extra.append(f"{meta['count']} pers.")
    if meta.get("dwell_s") is not None:
        extra.append(f"{int(meta['dwell_s'])}s")
    if meta.get("direction"):
        extra.append(str(meta["direction"]))
    suffix = f" ({', '.join(extra)})" if extra else ""
    return (f"{rule.name} — {ctx}{suffix}").strip(" —") or rule.name


def evaluate_event(session: Session, event: Event) -> None:
    try:
        rules = session.exec(
            select(Rule).where(Rule.is_active == True, Rule.trigger == event.event_type)  # noqa: E712
        ).all()
    except Exception:
        logger.debug("[rule] lecture des règles impossible", exc_info=True)
        return

    if not rules:
        return

    now = datetime.utcnow() + timedelta(hours=getattr(settings, "RULE_TZ_OFFSET_HOURS", 0))
    meta = event.meta or {}

    for rule in rules:
        if rule.zone_id is not None and meta.get("zone_id") != rule.zone_id:
            continue
        if not _schedule_armed(rule.schedule, now):
            continue
        if not _conditions_met(rule.conditions, event):
            continue

        alert = Alert(
            event_id=event.id,
            kind=(rule.kind or "custom"),
            label=_label(rule, event),
            reason=rule.name,
            camera_id=event.camera_id,
            snapshot_url=event.snapshot_url,
        )
        session.add(alert)
        session.commit()
        session.refresh(alert)
        logger.info(f"[rule] alerte créée : règle={rule.name!r} kind={alert.kind} (event {event.id})")

        channels = rule.notify_channels or []
        if channels:
            _send_notifications(session, rule, alert, channels)


def _send_notifications(session: Session, rule: Rule, alert: Alert, channels) -> None:
    subject = f"[Osirion] {alert.kind} — {alert.label}"
    body = (
        f"Règle   : {rule.name}\n"
        f"Type    : {alert.kind}\n"
        f"Détail  : {alert.label}\n"
        f"Caméra  : {alert.camera_id}\n"
        f"Date    : {alert.created_at}\n"
    )
    sent = []
    try:
        if "email" in channels:
            ok, _ = send_email(subject, body)
            if ok:
                sent.append("email")
        if "webhook" in channels:
            ok, _ = send_webhook({
                "kind": alert.kind, "label": alert.label, "rule": rule.name,
                "camera_id": alert.camera_id, "alert_id": alert.id,
            })
            if ok:
                sent.append("webhook")
        if sent:
            alert.notified_at = datetime.utcnow()
            alert.notified_channel = ",".join(sent)
            session.add(alert)
            session.commit()
    except Exception:
        logger.warning("[rule] envoi de notification échoué", exc_info=True)

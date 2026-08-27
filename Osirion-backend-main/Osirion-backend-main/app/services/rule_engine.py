# app/services/rule_engine.py
"""
Moteur de règles — évalué À L'INGESTION d'un événement (POST /events/add).

Pour chaque règle active dont le `trigger` == event_type : vérifie la zone, la
plage horaire armée et les conditions (contre event.meta) ; si tout matche ET que
la règle n'est pas en temporisation (cooldown), crée une Alerte avec la sévérité
de la règle et, si demandé, envoie les notifications (email/webhook).

Conditions — deux formats acceptés (composables) :
  • hérité       : {"min_count": 5} | {"min_wait_s": 300} | {"direction": "in"}
  • prédicats    : {"all": [{"field": "count", "op": ">=", "value": 5}, …],
                    "any": [{"field": "direction", "op": "==", "value": "in"}, …]}
    "all" = tous vrais (ET), "any" = au moins un vrai (OU).
    op ∈ >= > <= < == != between(value=[lo,hi]) in(value=[…]).

Best-effort : ne lève JAMAIS vers l'appelant (l'enregistrement d'un événement ne
doit pas échouer à cause d'une règle).
"""
import logging
import time as _time
from datetime import datetime, time, timedelta
from typing import Dict, Tuple

from sqlmodel import Session, select

from app.models.rules import Rule
from app.models.alerts import Alert
from app.models.events import Event
from app.services.notification_service import send_email, send_webhook, snapshot_local_path
from app.config import settings

logger = logging.getLogger(__name__)

# Anti-spam : dernier déclenchement (horloge monotone) par (rule_id, zone/line).
# En mémoire process — best-effort, remis à zéro au redémarrage (acceptable).
_last_fire: Dict[Tuple, float] = {}


# ── Plage horaire ────────────────────────────────────────────────────────────
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


# ── Conditions (prédicats typés + format hérité) ─────────────────────────────
def _to_num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


_NUM_OPS = {
    ">=": lambda a, b: a >= b,
    ">":  lambda a, b: a > b,
    "<=": lambda a, b: a <= b,
    "<":  lambda a, b: a < b,
}


def _eval_predicate(pred, meta) -> bool:
    """Évalue un prédicat {field, op, value} contre event.meta. Prudence : tout
    prédicat mal formé ou opérateur inconnu → False (ne déclenche pas par erreur)."""
    if not isinstance(pred, dict):
        return False
    field = pred.get("field")
    op = pred.get("op")
    expected = pred.get("value")
    actual = meta.get(field)

    if op in _NUM_OPS:
        a, b = _to_num(actual), _to_num(expected)
        return a is not None and b is not None and _NUM_OPS[op](a, b)
    if op == "==":
        return actual == expected
    if op == "!=":
        return actual != expected
    if op == "between":
        a = _to_num(actual)
        if a is None or not isinstance(expected, (list, tuple)) or len(expected) != 2:
            return False
        lo, hi = _to_num(expected[0]), _to_num(expected[1])
        return lo is not None and hi is not None and lo <= a <= hi
    if op == "in":
        return isinstance(expected, (list, tuple)) and actual in expected
    return False


def _legacy_ok(cond, meta) -> bool:
    """Format hérité (rétro-compatibilité des règles créées avant les prédicats)."""
    if "min_count" in cond and (_to_num(meta.get("count")) or 0) < cond["min_count"]:
        return False
    if "min_wait_s" in cond and (_to_num(meta.get("dwell_s")) or 0) < cond["min_wait_s"]:
        return False
    if "direction" in cond and meta.get("direction") != cond["direction"]:
        return False
    return True


def _conditions_met(cond, event: Event) -> bool:
    cond = cond or {}
    meta = event.meta or {}
    if not _legacy_ok(cond, meta):
        return False
    all_preds = cond.get("all")
    if isinstance(all_preds, list) and not all(_eval_predicate(p, meta) for p in all_preds):
        return False
    any_preds = cond.get("any")
    if isinstance(any_preds, list) and any_preds and not any(_eval_predicate(p, meta) for p in any_preds):
        return False
    return True


# ── Cooldown ─────────────────────────────────────────────────────────────────
def _cooldown_key(rule: Rule, meta) -> Tuple:
    z = meta.get("zone_id")
    if z is None:
        z = meta.get("line_id")
    return (rule.id, z)


def _in_cooldown(rule: Rule, meta, now_mono: float) -> bool:
    """Vrai si la règle a déjà tiré sur cette zone il y a moins de cooldown_s.
    Enregistre le tir courant si autorisé (effet de bord volontaire)."""
    cd = rule.cooldown_s or 0
    if cd <= 0:
        return False
    key = _cooldown_key(rule, meta)
    last = _last_fire.get(key)
    if last is not None and (now_mono - last) < cd:
        return True
    _last_fire[key] = now_mono
    return False


# ── Libellé ──────────────────────────────────────────────────────────────────
def _label(rule: Rule, event: Event) -> str:
    meta = event.meta or {}
    ctx = meta.get("zone_name") or meta.get("line_name") or ""
    extra = []
    if meta.get("count") is not None and meta.get("minimum") is None:
        extra.append(f"{meta['count']} pers.")
    if meta.get("dwell_s") is not None:
        extra.append(f"{int(meta['dwell_s'])}s")
    if meta.get("vacant_s") is not None:
        extra.append(f"vide depuis {int(meta['vacant_s'])}s")
    if meta.get("absence_s") is not None:
        extra.append(f"absence {int(meta['absence_s'])}s")
    if meta.get("minimum") is not None and meta.get("maximum") is not None:
        extra.append(
            f"effectif {meta.get('count', 0)}/{meta['maximum']} "
            f"(minimum {meta['minimum']})"
        )
    if meta.get("shortage_s") is not None:
        extra.append(f"sous-effectif {int(meta['shortage_s'])}s")
    if meta.get("direction"):
        extra.append(str(meta["direction"]))
    suffix = f" ({', '.join(extra)})" if extra else ""
    return (f"{rule.name} — {ctx}{suffix}").strip(" —") or rule.name


# ── Évaluation ───────────────────────────────────────────────────────────────
def _scope_matches(rule: Rule, meta) -> bool:
    """Vérifie les portées zone et groupe sans dépendre de la base.

    POST_VACANT et STAFFING_LOW portent ``schedule_id`` dans leurs métadonnées.
    La portée de groupe reste ainsi stable même lorsque des caméras sont ajoutées
    ou retirées du régime partagé.
    """
    meta = meta or {}
    if rule.zone_id is not None and meta.get("zone_id") != rule.zone_id:
        return False
    if (
        rule.work_schedule_id is not None
        and meta.get("schedule_id") != rule.work_schedule_id
    ):
        return False
    return True


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
    now_mono = _time.monotonic()
    meta = event.meta or {}

    for rule in rules:
        if not _scope_matches(rule, meta):
            continue
        if not _schedule_armed(rule.schedule, now):
            continue
        if not _conditions_met(rule.conditions, event):
            continue
        if _in_cooldown(rule, meta, now_mono):
            logger.debug(f"[rule] {rule.name!r} en cooldown ({rule.cooldown_s}s) → alerte ignorée")
            continue

        alert = Alert(
            event_id=event.id,
            kind=(rule.kind or "custom"),
            severity=(rule.severity or "warning"),
            label=_label(rule, event),
            reason=rule.name,
            camera_id=event.camera_id,
            snapshot_url=event.snapshot_url,
        )
        session.add(alert)
        # Observabilité : trace du dernier tir + compteur.
        rule.trigger_count = (rule.trigger_count or 0) + 1
        rule.last_triggered_at = datetime.utcnow()
        session.add(rule)
        session.commit()
        session.refresh(alert)
        logger.info(
            f"[rule] alerte créée : règle={rule.name!r} sévérité={alert.severity} "
            f"kind={alert.kind} (event {event.id})"
        )

        channels = rule.notify_channels or []
        if channels:
            _send_notifications(session, rule, alert, channels)


def _send_notifications(session: Session, rule: Rule, alert: Alert, channels) -> None:
    snap_path = snapshot_local_path(alert.snapshot_url)
    subject = f"[Osirion] {alert.severity.upper()} · {alert.kind} — {alert.label}"
    body = (
        f"Règle    : {rule.name}\n"
        f"Sévérité : {alert.severity}\n"
        f"Type     : {alert.kind}\n"
        f"Détail   : {alert.label}\n"
        f"Caméra   : {alert.camera_id}\n"
        f"Date     : {alert.created_at}\n"
        f"Capture  : {'jointe à cet email' if snap_path else '—'}\n"
    )
    sent = []
    try:
        if "email" in channels:
            ok, _ = send_email(subject, body, attachment_path=snap_path)
            if ok:
                sent.append("email")
        if "webhook" in channels:
            ok, _ = send_webhook({
                "kind": alert.kind, "severity": alert.severity, "label": alert.label,
                "rule": rule.name, "camera_id": alert.camera_id, "alert_id": alert.id,
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

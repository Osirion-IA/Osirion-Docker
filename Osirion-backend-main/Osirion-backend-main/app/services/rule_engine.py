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
from app.services.notification_service import (
    send_email, send_webhook, snapshot_local_path, compose_alert_email,
)
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


# ── Épisodes : une alerte par SITUATION, pas par événement ───────────────────
# Certains déclencheurs décrivent un ÉTAT et se répètent tant qu'il dure :
# CROWD_DETECTED est réémis à chaque passage du moteur tant que la file reste
# au-dessus du seuil. Le cooldown ne faisait que cadencer ce flux — une file
# saturée une heure produisait une alerte toutes les 2 min, soit 30 alertes pour
# UNE situation. Mesuré avant correction : 8 278 événements → 1 557 alertes,
# avec une médiane de 7 min entre deux alertes d'une même caméra (minimum 24 s).
#
# On regroupe donc ces événements en épisodes : UNE alerte à l'ouverture, plus
# rien tant que la situation dure. L'épisode est considéré clos après
# EPISODE_RESOLVE_AFTER_S sans nouvel événement (il n'existe pas d'événement de
# « fin de saturation » à écouter).
#
# ⚠ Ce traitement ne vaut QUE pour les déclencheurs répétitifs. POST_VACANT,
# lui, n'est émis qu'UNE fois par épisode, en amont, par le Core : lui imposer
# une durée minimale de persistance supprimerait purement et simplement les
# alertes d'absence. Les autres déclencheurs gardent donc le cooldown d'origine.
_STATE_TRIGGERS = {"CROWD_DETECTED"}

# Durée pendant laquelle la condition doit tenir avant la première alerte : une
# file à 10 personnes pendant 15 s n'est pas un incident.
EPISODE_MIN_DURATION_S = int(getattr(settings, "RULE_EPISODE_MIN_DURATION_S", 0) or 45)
# Silence au-delà duquel on considère la situation terminée.
EPISODE_RESOLVE_AFTER_S = int(getattr(settings, "RULE_EPISODE_RESOLVE_AFTER_S", 0) or 300)

# clé (rule_id, zone) → {first_seen, last_seen, alerted}
_episodes: Dict[Tuple, dict] = {}


def _episode_allows_alert(rule: Rule, meta, now_mono: float) -> bool:
    """Vrai s'il faut alerter MAINTENANT pour cette situation.

    En mémoire, comme le cooldown : un redémarrage rouvre les épisodes, ce qui
    coûte au pire une alerte de plus par zone — préférable à un état persisté
    qui resterait bloqué « ouvert » après un arrêt brutal.
    """
    key = _cooldown_key(rule, meta)
    ep = _episodes.get(key)

    if ep is None or (now_mono - ep["last_seen"]) > EPISODE_RESOLVE_AFTER_S:
        # Première occurrence, ou situation précédente résolue depuis longtemps.
        _episodes[key] = {"first_seen": now_mono, "last_seen": now_mono, "alerted": False}
        ep = _episodes[key]
    else:
        ep["last_seen"] = now_mono

    if ep["alerted"]:
        return False                      # déjà signalée, la situation se prolonge
    if (now_mono - ep["first_seen"]) < EPISODE_MIN_DURATION_S:
        return False                      # pas encore assez persistante
    ep["alerted"] = True
    return True


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
        if event.event_type in _STATE_TRIGGERS:
            # Déclencheur d'ÉTAT : une alerte par épisode (cf. _episode_allows_alert).
            if not _episode_allows_alert(rule, meta, now_mono):
                logger.debug(f"[rule] {rule.name!r} : épisode déjà signalé ou trop bref → alerte ignorée")
                continue
        elif _in_cooldown(rule, meta, now_mono):
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


# Reprise : délai croissant puis abandon. Plafonné à 30 min car une alerte de
# terrain perd sa valeur si elle arrive des heures plus tard — mieux vaut renoncer
# explicitement (et l'afficher comme non délivrée) que notifier trop tard.
NOTIFY_MAX_ATTEMPTS = 5
_NOTIFY_BACKOFF_MIN = (1, 5, 15, 30)


def _prochain_essai(tentatives: int):
    """Date de la prochaine reprise, ou None une fois les tentatives épuisées."""
    if tentatives >= NOTIFY_MAX_ATTEMPTS:
        return None
    minutes = _NOTIFY_BACKOFF_MIN[min(tentatives - 1, len(_NOTIFY_BACKOFF_MIN) - 1)]
    return datetime.utcnow() + timedelta(minutes=minutes)


def _send_notifications(session: Session, rule: Rule, alert: Alert, channels) -> None:
    requested = [c for c in ("email", "webhook") if c in channels]
    alert.notify_requested_channels = ",".join(requested) or None
    snap_path = snapshot_local_path(alert.snapshot_url)
    subject, body = compose_alert_email(alert)
    sent = []
    erreur = None
    try:
        if "email" in requested:
            ok, detail = send_email(subject, body, attachment_path=snap_path)
            if ok:
                sent.append("email")
            else:
                erreur = f"email: {detail}"
        if "webhook" in requested:
            ok, detail = send_webhook({
                "kind": alert.kind, "severity": alert.severity, "label": alert.label,
                "rule": rule.name, "camera_id": alert.camera_id, "alert_id": alert.id,
            })
            if ok:
                sent.append("webhook")
            else:
                erreur = f"{erreur + ' | ' if erreur else ''}webhook: {detail}"
    except Exception as e:  # noqa: BLE001 — l'échec ne doit jamais perdre l'alerte
        erreur = f"{type(e).__name__}: {e}"
        logger.warning("[rule] envoi de notification échoué", exc_info=True)

    alert.notify_attempts = (alert.notify_attempts or 0) + 1
    if sent:
        alert.notified_at = datetime.utcnow()
        alert.notified_channel = ",".join(sent)
        alert.notify_next_retry_at = None
        alert.notify_last_error = None
    else:
        # Aucun canal n'a abouti. On PROGRAMME une reprise au lieu d'abandonner :
        # les 55 alertes perdues de la campagne d'août 2026 l'ont été sur des
        # coupures DNS de quelques secondes, parfaitement rattrapables.
        alert.notify_last_error = (erreur or "aucun canal n'a abouti")[:255]
        alert.notify_next_retry_at = _prochain_essai(alert.notify_attempts)
        logger.warning(
            "[rule] alerte %s non notifiée (tentative %d) : %s — reprise prévue à %s",
            alert.id, alert.notify_attempts, alert.notify_last_error,
            alert.notify_next_retry_at,
        )
    session.add(alert)
    session.commit()

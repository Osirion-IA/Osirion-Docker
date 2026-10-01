# app/services/notification_retry.py
"""
Reprise des notifications d'alerte échouées (thread de fond).

Pourquoi. Campagne d'observation d'août 2026 : 55 alertes sur 574 n'ont jamais
été délivrées. Toutes de type « saturation de file », toutes sur des coupures DNS
passagères du serveur de messagerie — le lien internet du site, la même cause que
les refus de la passerelle vidéo. L'envoi n'était tenté qu'UNE fois : un hoquet de
quelques secondes perdait l'alerte définitivement, et rien dans l'interface ne le
signalait.

Ce thread rejoue les envois dont l'heure de reprise est échue, avec un délai
croissant (1, 5, 15 puis 30 min) et un abandon après NOTIFY_MAX_ATTEMPTS. Le
plafond est volontairement court : une alerte de terrain qui arrive des heures
plus tard n'a plus de valeur — mieux vaut renoncer explicitement et l'afficher
comme non délivrée que la livrer hors délai.

La reprise respecte strictement les canaux demandés par la règle d'origine. Un
canal ajouté plus tard ne doit pas recevoir rétroactivement une alerte qui ne lui
était pas destinée.
"""
import logging
import threading
import time
from datetime import datetime

from sqlmodel import Session, select

from app.config import settings
from app.database import engine
from app.models.alerts import Alert
from app.services.notification_service import (
    email_configured, send_email, send_webhook, snapshot_local_path,
    compose_alert_email,
    webhook_configured,
)
from app.services.rule_engine import NOTIFY_MAX_ATTEMPTS, _prochain_essai

logger = logging.getLogger(__name__)

_started = False
_start_lock = threading.Lock()
_thread: threading.Thread | None = None


def is_running() -> bool:
    return _thread is not None and _thread.is_alive()


def _canaux_disponibles() -> list:
    """Canaux réellement exploitables d'après la configuration en base."""
    canaux = []
    if email_configured():
        canaux.append("email")
    if webhook_configured():
        canaux.append("webhook")
    return canaux


def _canaux_alert(alert: Alert, disponibles: list) -> list:
    demandes = {
        c.strip() for c in (alert.notify_requested_channels or "").split(",")
        if c.strip()
    }
    return [c for c in disponibles if c in demandes]


def _rejouer(session: Session, alert: Alert, canaux: list) -> bool:
    """Retente la livraison d'une alerte. Renvoie True si un canal a abouti."""
    sujet, corps = compose_alert_email(alert)
    envoyes, erreur = [], None
    try:
        if "email" in canaux:
            ok, detail = send_email(
                sujet, corps, attachment_path=snapshot_local_path(alert.snapshot_url)
            )
            if ok:
                envoyes.append("email")
            else:
                erreur = f"email: {detail}"
        if "webhook" in canaux:
            ok, detail = send_webhook({
                "kind": alert.kind, "severity": alert.severity, "label": alert.label,
                "rule": alert.reason, "camera_id": alert.camera_id, "alert_id": alert.id,
            })
            if ok:
                envoyes.append("webhook")
            else:
                erreur = f"{erreur + ' | ' if erreur else ''}webhook: {detail}"
    except Exception as e:  # noqa: BLE001 — jamais fatal
        erreur = f"{type(e).__name__}: {e}"

    alert.notify_attempts = (alert.notify_attempts or 0) + 1
    if envoyes:
        alert.notified_at = datetime.utcnow()
        alert.notified_channel = ",".join(envoyes)
        alert.notify_next_retry_at = None
        alert.notify_last_error = None
    else:
        alert.notify_last_error = (erreur or "aucun canal n'a abouti")[:255]
        alert.notify_next_retry_at = _prochain_essai(alert.notify_attempts)
    session.add(alert)
    session.commit()
    return bool(envoyes)


def rejouer_les_echecs(session: Session) -> dict:
    """Un cycle de reprise. Extrait pour être testable et déclenchable à la main."""
    disponibles = _canaux_disponibles()
    if not disponibles:
        return {"reprises": 0, "reussies": 0, "abandonnees": 0,
                "motif": "aucun canal de notification configuré"}

    maintenant = datetime.utcnow()
    en_attente = session.exec(
        select(Alert).where(
            Alert.notified_at.is_(None),
            Alert.notify_next_retry_at.is_not(None),
            Alert.notify_next_retry_at <= maintenant,
            Alert.notify_attempts < NOTIFY_MAX_ATTEMPTS,
        ).order_by(Alert.created_at).limit(50)
    ).all()

    reussies = abandonnees = 0
    for alert in en_attente:
        canaux = _canaux_alert(alert, disponibles)
        if not canaux:
            # Conserver l'échéance : la reprise redeviendra possible lorsque le
            # canal demandé sera de nouveau configuré.
            continue
        if _rejouer(session, alert, canaux):
            reussies += 1
        elif alert.notify_next_retry_at is None:
            abandonnees += 1
    return {"reprises": len(en_attente), "reussies": reussies,
            "abandonnees": abandonnees}


def _loop(interval_s: int) -> None:
    time.sleep(min(interval_s, 90))  # laisse le backend finir de démarrer
    while True:
        try:
            with Session(engine) as session:
                stats = rejouer_les_echecs(session)
            if stats.get("reprises"):
                logger.info("[notify-retry] %s", stats)
            if stats.get("abandonnees"):
                logger.error(
                    "[notify-retry] %d alerte(s) ABANDONNÉE(S) après %d tentatives — "
                    "elles resteront marquées non délivrées.",
                    stats["abandonnees"], NOTIFY_MAX_ATTEMPTS,
                )
        except Exception:  # noqa: BLE001 — jamais fatal pour le thread
            logger.warning("[notify-retry] cycle en échec (réessai au prochain).",
                           exc_info=True)
        time.sleep(interval_s)


def start_notification_retry() -> None:
    """Démarre (une seule fois par processus) le thread de reprise."""
    global _started, _thread
    secondes = int(getattr(settings, "NOTIFY_RETRY_SECONDS", 60) or 0)
    if secondes <= 0:
        logger.info("[notify-retry] désactivée (NOTIFY_RETRY_SECONDS=0).")
        return
    with _start_lock:
        if _started:
            return
        _started = True
        _thread = threading.Thread(target=_loop, args=(secondes,), daemon=True,
                                   name="notify-retry")
        _thread.start()
    logger.info("[notify-retry] active (cycle %ds, %d tentatives max).",
                secondes, NOTIFY_MAX_ATTEMPTS)

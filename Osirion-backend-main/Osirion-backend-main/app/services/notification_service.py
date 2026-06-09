# app/services/notification_service.py
"""
Envoi de notifications d'alerte (email / webhook).

⚠️ POLITIQUE : ces fonctions ne sont appelées QUE depuis l'action utilisateur
POST /alerts/{id}/notify. Aucune notification n'est jamais envoyée
automatiquement par le système.

Implémentation SANS dépendance externe :
  - email   : smtplib (bibliothèque standard)
  - webhook : urllib.request (bibliothèque standard)

Chaque fonction est défensive : elle ne lève pas, et retourne (ok, message) afin
que l'API puisse répondre proprement (200 succès / 400 mal configuré / 502 échec).
"""
import json
import smtplib
import ssl
import urllib.request
import logging
from email.message import EmailMessage
from typing import Optional, Tuple

from app.config import settings

logger = logging.getLogger(__name__)

_TIMEOUT = 10  # secondes


def email_configured() -> bool:
    return bool(settings.SMTP_HOST and (settings.ALERT_EMAIL_TO or "").strip())


def webhook_configured() -> bool:
    return bool((settings.ALERT_WEBHOOK_URL or "").strip())


def send_email(subject: str, body: str, to: Optional[str] = None) -> Tuple[bool, str]:
    """Envoie un email texte. `to` peut surcharger ALERT_EMAIL_TO (liste séparée
    par des virgules). Retourne (ok, message)."""
    recipients = (to or settings.ALERT_EMAIL_TO or "").strip()
    if not settings.SMTP_HOST:
        return False, "SMTP non configuré (SMTP_HOST vide)."
    if not recipients:
        return False, "Aucun destinataire (ALERT_EMAIL_TO vide)."

    rcpt_list = [r.strip() for r in recipients.split(",") if r.strip()]
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.SMTP_FROM
    msg["To"] = ", ".join(rcpt_list)
    msg.set_content(body)

    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=_TIMEOUT) as server:
            if settings.SMTP_USE_TLS:
                server.starttls(context=ssl.create_default_context())
            if settings.SMTP_USER:
                server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.send_message(msg)
        logger.info(f"[notify] email envoyé à {rcpt_list} (sujet={subject!r})")
        return True, f"Email envoyé à {len(rcpt_list)} destinataire(s)."
    except Exception as e:
        logger.error(f"[notify] échec envoi email : {e}")
        return False, f"Échec envoi email : {e}"


def send_webhook(payload: dict) -> Tuple[bool, str]:
    """POST le payload JSON au ALERT_WEBHOOK_URL configuré. Retourne (ok, message)."""
    url = (settings.ALERT_WEBHOOK_URL or "").strip()
    if not url:
        return False, "Webhook non configuré (ALERT_WEBHOOK_URL vide)."
    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url, data=data, headers={"Content-Type": "application/json"}, method="POST"
        )
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            code = resp.getcode()
        logger.info(f"[notify] webhook POST {url} → HTTP {code}")
        if 200 <= code < 300:
            return True, f"Webhook notifié (HTTP {code})."
        return False, f"Webhook a répondu HTTP {code}."
    except Exception as e:
        logger.error(f"[notify] échec webhook : {e}")
        return False, f"Échec webhook : {e}"

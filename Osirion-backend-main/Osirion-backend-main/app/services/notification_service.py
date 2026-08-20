# app/services/notification_service.py
"""
Envoi de notifications d'alerte (email / webhook).

⚠️ POLITIQUE : ces fonctions sont appelées (1) sur action utilisateur explicite
POST /alerts/{id}/notify, et (2) AUTOMATIQUEMENT par le moteur de règles quand une
règle définit des `notify_channels` (email/webhook) — avec un COOLDOWN par règle
qui borne le débit (pas d'envoi en masse non contrôlé).

CONFIG : les paramètres SMTP/webhook viennent de la CONFIG EFFECTIVE — la table
`notification_config` (saisie depuis Paramètres → Notifications) si renseignée,
sinon repli sur le .env/settings. En cache mémoire, invalidée à l'enregistrement.

Implémentation SANS dépendance externe :
  - email   : smtplib (bibliothèque standard) — pièce jointe screenshot supportée
  - webhook : urllib.request (bibliothèque standard)

Chaque fonction est défensive : elle ne lève pas, et retourne (ok, message) afin
que l'API puisse répondre proprement (200 succès / 400 mal configuré / 502 échec).
"""
import json
import smtplib
import ssl
import urllib.request
import logging
import mimetypes
import threading
from pathlib import Path
from email.message import EmailMessage
from typing import Optional, Tuple

from sqlmodel import Session

from app.config import settings
from app.database import engine
from app.utils.security_utils import decrypter

logger = logging.getLogger(__name__)

_TIMEOUT = 10  # secondes


# ─────────────────────────────────────────────
# Config effective (base notification_config prioritaire, sinon .env), cachée
# ─────────────────────────────────────────────
_cfg_cache: "dict | None" = None
_cfg_lock = threading.Lock()


def _load_effective_config() -> dict:
    """Fusionne la config de notification base (prioritaire) et .env (repli)."""
    host = user = password = frm = email_to = webhook = None
    port = None
    use_tls = None
    source = "env"
    try:
        from app.models.notification_config import NotificationConfig  # import tardif (évite cycles)
        with Session(engine) as s:
            row = s.get(NotificationConfig, 1)
        if row and (row.smtp_host or row.smtp_user or row.alert_email_to
                    or row.smtp_password_enc or row.alert_webhook_url):
            host = row.smtp_host or None
            port = row.smtp_port
            user = row.smtp_user or None
            password = decrypter(row.smtp_password_enc) if row.smtp_password_enc else None
            frm = row.smtp_from or None
            use_tls = row.smtp_use_tls
            email_to = row.alert_email_to or None
            webhook = row.alert_webhook_url or None
            source = "db"
    except Exception:
        # Table absente (avant migration) ou DB indispo → repli .env, jamais bloquant.
        logger.debug("[notify] lecture config base impossible → repli .env", exc_info=True)
    return {
        "smtp_host": host or settings.SMTP_HOST,
        "smtp_port": port if port is not None else settings.SMTP_PORT,
        "smtp_user": user if user is not None else settings.SMTP_USER,
        "smtp_password": password if password is not None else settings.SMTP_PASSWORD,
        "smtp_from": frm or settings.SMTP_FROM,
        "smtp_use_tls": use_tls if use_tls is not None else settings.SMTP_USE_TLS,
        "alert_email_to": email_to if email_to is not None else settings.ALERT_EMAIL_TO,
        "alert_webhook_url": webhook if webhook is not None else settings.ALERT_WEBHOOK_URL,
        "source": source,
    }


def get_config() -> dict:
    global _cfg_cache
    with _cfg_lock:
        if _cfg_cache is None:
            _cfg_cache = _load_effective_config()
        return _cfg_cache


def invalidate_config() -> None:
    """À appeler après tout enregistrement de la config de notification (UI)."""
    global _cfg_cache
    with _cfg_lock:
        _cfg_cache = None


def email_configured() -> bool:
    c = get_config()
    return bool(c["smtp_host"] and (c["alert_email_to"] or "").strip())


def webhook_configured() -> bool:
    return bool((get_config()["alert_webhook_url"] or "").strip())


def snapshot_local_path(snapshot_url: Optional[str]) -> Optional[str]:
    """Chemin disque LOCAL d'un snapshot d'alerte (à joindre au mail), ou None.
    `snapshot_url` est soit une URL http (distante → non joignable localement),
    soit un chemin relatif ('snapshots/xxx.jpg') servi depuis le CWD (/app)."""
    if not snapshot_url:
        return None
    s = str(snapshot_url)
    if s.startswith("http"):
        return None
    try:
        p = Path(s.lstrip("/"))
        return str(p) if p.is_file() else None
    except Exception:
        return None


def send_email(subject: str, body: str, to: Optional[str] = None,
               attachment_path: Optional[str] = None, cfg: Optional[dict] = None) -> Tuple[bool, str]:
    """Envoie un email texte, avec une PIÈCE JOINTE facultative (ex. le screenshot
    de l'alerte). `to` peut surcharger le(s) destinataire(s) par défaut (liste
    séparée par des virgules). `cfg` permet de forcer une config (test de valeurs
    non encore enregistrées) ; sinon config effective. Retourne (ok, message). La
    pièce jointe est défensive : si le fichier manque/illisible, l'email part quand même."""
    cfg = cfg or get_config()
    recipients = (to or cfg["alert_email_to"] or "").strip()
    if not cfg["smtp_host"]:
        return False, "SMTP non configuré (hôte vide)."
    if not recipients:
        return False, "Aucun destinataire (liste vide)."

    rcpt_list = [r.strip() for r in recipients.split(",") if r.strip()]
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = cfg["smtp_from"]
    msg["To"] = ", ".join(rcpt_list)
    msg.set_content(body)

    if attachment_path:
        try:
            p = Path(attachment_path)
            if p.is_file():
                ctype, _ = mimetypes.guess_type(str(p))
                maintype, subtype = (ctype or "image/jpeg").split("/", 1)
                msg.add_attachment(p.read_bytes(), maintype=maintype,
                                   subtype=subtype, filename=p.name)
        except Exception as e:
            logger.warning(f"[notify] pièce jointe ignorée ({attachment_path}) : {e}")

    try:
        with smtplib.SMTP(cfg["smtp_host"], cfg["smtp_port"], timeout=_TIMEOUT) as server:
            if cfg["smtp_use_tls"]:
                server.starttls(context=ssl.create_default_context())
            if cfg["smtp_user"]:
                server.login(cfg["smtp_user"], cfg["smtp_password"])
            server.send_message(msg)
        logger.info(f"[notify] email envoyé à {rcpt_list} (sujet={subject!r})")
        return True, f"Email envoyé à {len(rcpt_list)} destinataire(s)."
    except Exception as e:
        logger.error(f"[notify] échec envoi email : {e}")
        return False, f"Échec envoi email : {e}"


def send_webhook(payload: dict) -> Tuple[bool, str]:
    """POST le payload JSON au webhook configuré. Retourne (ok, message)."""
    url = (get_config()["alert_webhook_url"] or "").strip()
    if not url:
        return False, "Webhook non configuré (URL vide)."
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

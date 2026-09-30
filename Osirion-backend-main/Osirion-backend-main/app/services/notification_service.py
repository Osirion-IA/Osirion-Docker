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
import re
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


# ─────────────────────────────────────────────
# Composition du message d'alerte
# ─────────────────────────────────────────────
# Le mail s'adresse à un agent sur le terrain, pas à un intégrateur. Il ne porte
# donc QUE : ce qui s'est passé, où, quand — et la capture en pièce jointe.
#
# Ont été retirés parce qu'ils n'aident aucune décision sur le terrain :
#   - les décomptes de personnes (« (14 pers.) », « (vide depuis 902s) »), collés
#     en fin de libellé par le moteur de règles ;
#   - le type interne (`kind`), la sévérité, le statut, l'identifiant de caméra,
#     le nom de la règle, le motif (qui répète le libellé) et le numéro de
#     tentative de reprise.

_TRAILING_PAREN = re.compile(r"\s*\([^()]*\)\s*$")


def _plain_label(label: Optional[str]) -> str:
    """Libellé sans sa parenthèse finale de comptage/durée.

    « Saturation de file d'attente — FA (14 pers.) » → « … — FA »
    « Poste d'agent vacant — PR - Diffa (vide depuis 902s) » → « … — PR - Diffa »
    """
    return _TRAILING_PAREN.sub("", (label or "Alerte").strip()) or "Alerte"


def _alert_context(alert) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """(nom de caméra, site, fuseau) — défensif : jamais bloquant.

    Le fuseau est cherché d'abord sur la ZONE d'où vient l'alerte (les postes
    d'agent portent leur régime horaire, et c'est là que l'heure compte), puis
    sur le régime de staffing de la caméra. Sans repère, l'appelant marquera UTC.
    """
    camera_id = getattr(alert, "camera_id", None)
    if camera_id is None:
        return None, None, None
    try:
        from sqlalchemy.orm import selectinload
        from sqlmodel import select
        from app.models.cameras import Camera
        from app.models.events import Event
        from app.models.zones import Zone
        from app.models.work_schedule import WorkSchedule

        with Session(engine) as s:
            cam = s.exec(
                select(Camera).where(Camera.id == camera_id).options(selectinload(Camera.groups))
            ).first()
            if cam is None:
                return None, None, None
            site = cam.groups[0].name if cam.groups else None

            schedule_id = None
            event_id = getattr(alert, "event_id", None)
            if event_id:
                event = s.get(Event, event_id)
                zone_id = (getattr(event, "meta", None) or {}).get("zone_id") if event else None
                if zone_id is not None:
                    zone = s.get(Zone, zone_id)
                    schedule_id = getattr(zone, "work_schedule_id", None) if zone else None
            schedule_id = schedule_id or cam.staffing_work_schedule_id

            tz = None
            if schedule_id:
                ws = s.get(WorkSchedule, schedule_id)
                tz = getattr(ws, "timezone", None) if ws else None
            return cam.cam_name, site, tz
    except Exception:
        logger.debug("[notify] contexte d'alerte indisponible", exc_info=True)
        return None, None, None


def _local_time(when, tz_name: Optional[str]) -> str:
    """Horodatage lisible. Le parc est à cheval sur plusieurs fuseaux : on rend
    l'heure du SITE quand on la connaît, sinon on marque explicitement l'UTC
    plutôt que de laisser une heure sans repère."""
    if when is None:
        return "—"
    if tz_name:
        try:
            from zoneinfo import ZoneInfo
            from datetime import timezone
            local = when.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(tz_name))
            return local.strftime("%d/%m/%Y à %H:%M")
        except Exception:
            logger.debug("[notify] fuseau %s inutilisable", tz_name, exc_info=True)
    return when.strftime("%d/%m/%Y à %H:%M") + " UTC"


def compose_alert_email(alert) -> Tuple[str, str]:
    """(sujet, corps) épurés pour une alerte. La capture reste en pièce jointe."""
    titre = _plain_label(alert.label)
    cam_name, site, tz = _alert_context(alert)

    lignes = []
    if cam_name:
        lignes.append(f"Caméra : {cam_name}")
    if site:
        lignes.append(f"Site   : {site}")
    lignes.append(f"Heure  : {_local_time(getattr(alert, 'created_at', None), tz)}")
    return f"Osirion — {titre}", "\n".join(lignes) + "\n"


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

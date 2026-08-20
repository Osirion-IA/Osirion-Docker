# app/routes/notifications_routes.py
"""
Configuration des NOTIFICATIONS (email SMTP + webhook) depuis l'interface.

- GET  /notifications/config       : config actuelle (mot de passe JAMAIS renvoyé).
- PUT  /notifications/config       : enregistre (base prime sur .env ; mdp vide = conservé).
- POST /notifications/config/test  : envoie un email de TEST (valeurs saisies ou effectives).

Admin uniquement. Même pattern que hikcentral_routes (config effective + Fernet).
"""
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session

from app.database import get_session
from app.middleware.auth_middleware import require_admin
from app.models.notification_config import NotificationConfig
from app.services import notification_service as notif
from app.utils.security_utils import crypter

router = APIRouter()
logger = logging.getLogger(__name__)


class NotifConfigIn(BaseModel):
    """Champs saisis depuis l'UI. Tous optionnels ; smtp_password vide/omis =
    on conserve le mot de passe déjà enregistré. `to` sert uniquement au test."""
    smtp_host: Optional[str] = None
    smtp_port: Optional[int] = None
    smtp_user: Optional[str] = None
    smtp_password: Optional[str] = None
    smtp_from: Optional[str] = None
    smtp_use_tls: Optional[bool] = None
    alert_email_to: Optional[str] = None
    alert_webhook_url: Optional[str] = None
    to: Optional[str] = None


@router.get("/config")
def get_notif_config(_admin=Depends(require_admin), session: Session = Depends(get_session)):
    """Config actuelle. Le mot de passe n'est JAMAIS renvoyé (has_password)."""
    row = session.get(NotificationConfig, 1)
    cfg = notif.get_config()
    return {
        "smtp_host": row.smtp_host if row else None,
        "smtp_port": row.smtp_port if row else None,
        "smtp_user": row.smtp_user if row else None,
        "smtp_from": row.smtp_from if row else None,
        "smtp_use_tls": row.smtp_use_tls if row else None,
        "alert_email_to": row.alert_email_to if row else None,
        "alert_webhook_url": row.alert_webhook_url if row else None,
        "has_password": bool(row and row.smtp_password_enc),
        "source": cfg["source"],                       # "db" (UI) | "env" (repli)
        "email_configured": notif.email_configured(),
        "webhook_configured": notif.webhook_configured(),
        "effective": {                                 # ce qui est réellement utilisé
            "smtp_host": cfg["smtp_host"] or None,
            "smtp_port": cfg["smtp_port"],
            "smtp_from": cfg["smtp_from"] or None,
            "smtp_use_tls": cfg["smtp_use_tls"],
            "alert_email_to": cfg["alert_email_to"] or None,
        },
        "updated_at": row.updated_at.isoformat() if row and row.updated_at else None,
        "updated_by": row.updated_by if row else None,
    }


@router.put("/config")
def put_notif_config(
    payload: NotifConfigIn,
    admin=Depends(require_admin),
    session: Session = Depends(get_session),
):
    """Enregistre la config. Mot de passe vide/omis → on garde l'existant.
    Priorité base > .env dès qu'un champ est renseigné."""
    row = session.get(NotificationConfig, 1)
    if not row:
        row = NotificationConfig(id=1)
    row.smtp_host = (payload.smtp_host or "").strip() or None
    row.smtp_port = payload.smtp_port
    row.smtp_user = (payload.smtp_user or "").strip() or None
    row.smtp_from = (payload.smtp_from or "").strip() or None
    row.smtp_use_tls = payload.smtp_use_tls
    row.alert_email_to = (payload.alert_email_to or "").strip() or None
    row.alert_webhook_url = (payload.alert_webhook_url or "").strip() or None
    if payload.smtp_password and payload.smtp_password.strip():
        row.smtp_password_enc = crypter(payload.smtp_password.strip())   # (re)chiffre
    row.updated_at = datetime.utcnow()
    row.updated_by = getattr(admin, "email", None)
    session.add(row)
    session.commit()
    notif.invalidate_config()   # le service relira la nouvelle config
    return {
        "message": "Configuration enregistrée.",
        "email_configured": notif.email_configured(),
        "webhook_configured": notif.webhook_configured(),
        "has_password": bool(row.smtp_password_enc),
        "source": notif.get_config()["source"],
    }


@router.post("/config/test")
def test_notif_email(
    payload: Optional[NotifConfigIn] = Body(default=None),
    _admin=Depends(require_admin),
):
    """Envoie un email de TEST. Avec un corps → teste ces valeurs (avant
    enregistrement ; mot de passe non fourni → celui déjà enregistré/.env) ; sinon
    → teste la config effective. Ne modifie rien en base."""
    eff = notif.get_config()
    p = payload
    cfg = {
        "smtp_host": (p.smtp_host if p and p.smtp_host else eff["smtp_host"]),
        "smtp_port": (p.smtp_port if p and p.smtp_port is not None else eff["smtp_port"]),
        "smtp_user": (p.smtp_user if p and p.smtp_user is not None else eff["smtp_user"]),
        "smtp_password": (p.smtp_password if p and p.smtp_password else eff["smtp_password"]),
        "smtp_from": (p.smtp_from if p and p.smtp_from else eff["smtp_from"]),
        "smtp_use_tls": (p.smtp_use_tls if p and p.smtp_use_tls is not None else eff["smtp_use_tls"]),
        "alert_email_to": (p.alert_email_to if p and p.alert_email_to else eff["alert_email_to"]),
        "alert_webhook_url": eff["alert_webhook_url"],
        "source": eff["source"],
    }
    if not cfg["smtp_host"]:
        raise HTTPException(status_code=400, detail="Hôte SMTP requis.")
    to = (p.to.strip() if p and p.to and p.to.strip() else None)
    if not (to or (cfg["alert_email_to"] or "").strip()):
        raise HTTPException(status_code=400, detail="Aucun destinataire (renseignez « Destinataires » ou un email de test).")

    subject = "[Qwiper Sentinel] Email de test"
    body = (
        "Ceci est un email de TEST envoyé depuis Qwiper Sentinel.\n\n"
        "Si vous le recevez, la configuration SMTP est correcte : les alertes\n"
        "pourront vous être notifiées automatiquement (capture jointe le cas échéant).\n"
        f"\nEnvoyé le {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}.\n"
    )
    ok, msg = notif.send_email(subject, body, to=to, cfg=cfg)
    if not ok:
        raise HTTPException(status_code=502, detail=msg)
    return {"ok": True, "message": msg}

# app/routes/notifications_routes.py
"""
Configuration des NOTIFICATIONS (email SMTP + webhook) depuis l'interface.

- GET  /notifications/config       : config actuelle (mot de passe JAMAIS renvoyé).
- PUT  /notifications/config       : enregistre (base prime sur .env ; mdp vide = conservé).
- POST /notifications/config/test  : envoie un email de TEST (valeurs saisies ou effectives).

Admin uniquement. Même pattern que hikcentral_routes (config effective + Fernet).
"""
import logging
import re
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


# ─────────────────────────────────────────────
# Destinataires d'alerte : une LISTE, normalisée en amont du stockage
# ─────────────────────────────────────────────
# Le format de stockage reste une chaîne séparée par des virgules (c'est ce que
# send_email découpe) : aucune migration, aucun changement de contrat. Mais la
# saisie est normalisée ET validée ici, pas seulement dans l'UI — une adresse
# fautive n'échouait qu'au moment de l'envoi, avec une erreur SMTP illisible,
# et un point-virgule au lieu d'une virgule produisait UN destinataire bancal.
_EMAIL_RE = re.compile(r"^[^@\s,;]+@[^@\s,;]+\.[A-Za-z]{2,}$")
_SEPARATORS = re.compile(r"[,;\s]+")
MAX_RECIPIENTS_LEN = 1024   # = longueur de la colonne alert_email_to


def normalize_recipients(raw: Optional[str]) -> Optional[str]:
    """« a@x.com; B@X.COM , a@x.com » → « a@x.com, B@X.COM ».

    Accepte virgule, point-virgule, espace et retour à la ligne comme séparateurs.
    Déduplique sans tenir compte de la casse, en gardant la première écriture.
    Lève une 400 listant les entrées invalides plutôt que de stocker du bruit.
    """
    if raw is None:
        return None
    morceaux = [m for m in _SEPARATORS.split(raw.strip()) if m]
    if not morceaux:
        return None

    valides, invalides, vus = [], [], set()
    for m in morceaux:
        if not _EMAIL_RE.match(m):
            invalides.append(m)
            continue
        cle = m.lower()
        if cle not in vus:
            vus.add(cle)
            valides.append(m)

    if invalides:
        raise HTTPException(
            status_code=400,
            detail=("Adresse invalide : " if len(invalides) == 1 else "Adresses invalides : ")
                   + ", ".join(invalides),
        )
    joint = ", ".join(valides)
    if len(joint) > MAX_RECIPIENTS_LEN:
        raise HTTPException(
            status_code=400,
            detail=f"Trop de destinataires ({len(valides)}) : la liste dépasse {MAX_RECIPIENTS_LEN} caractères.",
        )
    return joint or None


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
    row.alert_email_to = normalize_recipients(payload.alert_email_to)
    row.alert_webhook_url = (payload.alert_webhook_url or "").strip() or None
    if payload.smtp_password and payload.smtp_password.strip():
        row.smtp_password_enc = crypter(payload.smtp_password.strip())   # (re)chiffre
    if row.smtp_password_enc and not (row.smtp_user or "").strip():
        raise HTTPException(
            status_code=400,
            detail="Utilisateur SMTP requis dès qu'un mot de passe est renseigné "
                   "(sans lui, l'authentification ne peut pas être tentée).",
        )
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
        "alert_email_to": (normalize_recipients(p.alert_email_to) if p and p.alert_email_to else eff["alert_email_to"]),
        "alert_webhook_url": eff["alert_webhook_url"],
        "source": eff["source"],
    }
    if not cfg["smtp_host"]:
        raise HTTPException(status_code=400, detail="Hôte SMTP requis.")
    to = (normalize_recipients(p.to) if p and p.to and p.to.strip() else None)
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

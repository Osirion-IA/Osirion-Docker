# app/routes/hikcentral_routes.py
"""
Connecteur HikCentral — source de flux caméras.

- GET  /hikcentral/status            : le connecteur est-il configuré ?
- POST /hikcentral/sync              : synchronise le catalogue (groupes + caméras).
- GET  /hikcentral/stream-url        : résout une URL RTSP standard (rtsp_s) fraîche
                                       pour une caméra du catalogue (appelée par le Core).
- POST /hikcentral/cameras/{id}/retry : ré-interroge HikCentral (contourne le cache) →
                                       vérifie la liaison agence + rafraîchit l'URL.
"""
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import Session

from app.config import settings
from app.database import get_session
from app.middleware.auth_middleware import require_user, require_admin
from app.models.cameras import Camera
from app.models.hikcentral_config import HikCentralConfig
from app.services import hikcentral_connector as hik
from app.services import hikcentral_scheduler as hik_scheduler
from app.services.hikcentral_sync import sync_catalog
from app.utils.security_utils import crypter


class HikConfigIn(BaseModel):
    """Infos de CONNEXION saisies depuis l'UI (Paramètres). Tous optionnels :
    app_secret vide/omis = on conserve le secret déjà enregistré."""
    host: Optional[str] = None
    app_key: Optional[str] = None
    app_secret: Optional[str] = None
    user_id: Optional[str] = None

router = APIRouter()
logger = logging.getLogger(__name__)


def _hik_camera_or_400(session: Session, cam_id: int) -> Camera:
    """Récupère une caméra HikCentral exploitable (existe + source hikcentral + index)."""
    camera = session.get(Camera, cam_id)
    if not camera:
        raise HTTPException(status_code=404, detail="Caméra non trouvée.")
    if camera.source_type != "hikcentral" or not camera.hik_index_code:
        raise HTTPException(
            status_code=400,
            detail="Cette caméra n'est pas une source HikCentral (URL non résolue par cette voie).",
        )
    if not hik.is_configured():
        raise HTTPException(status_code=400, detail="HikCentral non configuré (voir .env).")
    return camera


@router.get("/status")
def status(_user=Depends(require_user)):
    cfg = hik.get_config()
    return {
        "configured": hik.is_configured(),
        "host": cfg["host"] or None,
        "stream_type": cfg["stream_type"],   # 0=main, 1=sub
        "source": cfg["source"],             # "db" (UI) | "env" (repli)
        "sync_interval_minutes": settings.HIK_SYNC_INTERVAL_MINUTES,
        "periodic_running": hik_scheduler.is_running(),
    }


# ─────────────────────────────────────────────
# Configuration de connexion (saisie depuis l'UI — admin uniquement)
# ─────────────────────────────────────────────
@router.get("/config")
def get_connection_config(_admin=Depends(require_admin), session: Session = Depends(get_session)):
    """Config de connexion actuelle. Le secret n'est JAMAIS renvoyé (has_secret)."""
    row = session.get(HikCentralConfig, 1)
    cfg = hik.get_config()
    return {
        "host": row.host if row else None,
        "app_key": row.app_key if row else None,
        "user_id": row.user_id if row else None,
        "has_secret": bool(row and row.app_secret_enc),
        "source": cfg["source"],             # "db" | "env"
        "configured": hik.is_configured(),
        "effective_host": cfg["host"] or None,   # ce qui est réellement utilisé
        "updated_at": row.updated_at.isoformat() if row and row.updated_at else None,
        "updated_by": row.updated_by if row else None,
    }


@router.put("/config")
def put_connection_config(
    payload: HikConfigIn,
    admin=Depends(require_admin),
    session: Session = Depends(get_session),
):
    """Enregistre les infos de connexion. Secret vide/omis → on garde l'existant.
    Priorité base > .env dès qu'un champ est renseigné."""
    row = session.get(HikCentralConfig, 1)
    if not row:
        row = HikCentralConfig(id=1)
    row.host = (payload.host or "").strip() or None
    row.app_key = (payload.app_key or "").strip() or None
    row.user_id = (payload.user_id or "").strip() or None
    if payload.app_secret and payload.app_secret.strip():
        row.app_secret_enc = crypter(payload.app_secret.strip())   # (re)chiffre
    row.updated_at = datetime.utcnow()
    row.updated_by = getattr(admin, "email", None)
    session.add(row)
    session.commit()
    hik.invalidate_config()   # le connecteur relira la nouvelle config
    cfg = hik.get_config()
    return {
        "message": "Configuration enregistrée.",
        "configured": hik.is_configured(),
        "source": cfg["source"],
        "has_secret": bool(row.app_secret_enc),
    }


@router.post("/config/test")
def test_connection(
    payload: Optional[HikConfigIn] = Body(default=None),
    _admin=Depends(require_admin),
):
    """Teste la connexion HikCentral. Avec un corps → teste ces valeurs (avant
    enregistrement) ; sinon → teste la config effective actuelle. Le secret non
    fourni retombe sur celui déjà enregistré (ou .env)."""
    eff = hik.get_config()
    cfg = {
        "host": (payload.host if payload and payload.host else eff["host"]),
        "app_key": (payload.app_key if payload and payload.app_key else eff["app_key"]),
        "app_secret": (payload.app_secret if payload and payload.app_secret else eff["app_secret"]),
        "user_id": (payload.user_id if payload and payload.user_id else eff["user_id"]),
        "verify_ssl": eff["verify_ssl"],
    }
    try:
        hik.test_connection(cfg)
    except hik.HikCentralError as e:
        raise HTTPException(status_code=502, detail=f"Échec de connexion : {e}")
    return {"ok": True, "message": "Connexion HikCentral réussie."}


@router.post("/sync")
def sync(_user=Depends(require_user), session: Session = Depends(get_session)):
    """Synchronise le catalogue HikCentral (areas → groupes, caméras → catalogue)."""
    if not hik.is_configured():
        raise HTTPException(status_code=400, detail="HikCentral non configuré (voir .env : HIK_HOST / HIK_APP_KEY / HIK_APP_SECRET / HIK_USER_ID).")
    try:
        stats = sync_catalog(session)
    except hik.HikCentralError as e:
        raise HTTPException(status_code=502, detail=f"HikCentral : {e}")
    except Exception as e:  # noqa: BLE001
        logger.warning("[hik] échec de synchronisation", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erreur de synchronisation : {e}")
    return {"message": "Synchronisation terminée.", **stats}


@router.get("/stream-url")
def stream_url(
    cam: int = Query(..., description="ID interne de la caméra (catalogue)."),
    refresh: bool = Query(False, description="Ignorer le cache et ré-interroger HikCentral."),
    _user=Depends(require_user),
    session: Session = Depends(get_session),
):
    """URL RTSP standard (rtsp_s) fraîche pour une caméra HikCentral.

    Appelée par le Core à chaque cycle de supervision pour (ré)créer le relais
    MediaMTX. Cache TTL côté connecteur → HikCentral n'est pas sollicité à chaque
    appel. Les credentials sont EMBARQUÉS dans l'URL : endpoint réservé USER/ADMIN
    et service interne (jamais VIEWER).
    """
    camera = _hik_camera_or_400(session, cam)
    try:
        url = hik.resolve_stream_url(camera.hik_index_code, force=refresh)
    except hik.HikCentralError as e:
        raise HTTPException(status_code=502, detail=f"HikCentral : {e}")
    return {
        "cam_id": camera.id,
        "name": camera.cam_name,
        "index_code": camera.hik_index_code,
        "stream_type": settings.HIK_STREAM_TYPE,
        "url": url,
    }


@router.post("/cameras/{cam_id}/retry")
def retry_camera(
    cam_id: int,
    _user=Depends(require_user),
    session: Session = Depends(get_session),
):
    """Relance une caméra HikCentral instable (liaisons agences peu fiables).

    Contourne le cache et ré-interroge HikCentral : prouve que la liaison agence
    répond et rafraîchit l'URL en cache. Le Core, qui résout l'URL à chaque cycle,
    ré-applique l'URL fraîche → le relais MediaMTX redémarre si elle a changé.
    502 si HikCentral/la liaison ne répond pas (message exploitable côté UI).
    """
    camera = _hik_camera_or_400(session, cam_id)
    hik.invalidate_stream_url(camera.hik_index_code)
    try:
        url = hik.resolve_stream_url(camera.hik_index_code, force=True)
    except hik.HikCentralError as e:
        raise HTTPException(status_code=502, detail=f"HikCentral injoignable : {e}")
    return {
        "message": "Flux ré-interrogé avec succès.",
        "cam_id": camera.id,
        "name": camera.cam_name,
        "resolved": bool(url),
    }

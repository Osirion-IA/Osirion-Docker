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

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session

from app.config import settings
from app.database import get_session
from app.middleware.auth_middleware import require_user
from app.models.cameras import Camera
from app.services import hikcentral_connector as hik
from app.services import hikcentral_scheduler as hik_scheduler
from app.services.hikcentral_sync import sync_catalog

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
    return {
        "configured": hik.is_configured(),
        "host": settings.HIK_HOST or None,
        "stream_type": settings.HIK_STREAM_TYPE,  # 0=main, 1=sub
        "sync_interval_minutes": settings.HIK_SYNC_INTERVAL_MINUTES,
        "periodic_running": hik_scheduler.is_running(),
    }


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

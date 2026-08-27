from fastapi import APIRouter, HTTPException, Depends, Query
from sqlmodel import Session, select
from sqlalchemy import delete as sa_delete
from sqlalchemy.orm import selectinload
from typing import List, Optional

from app.models.cameras import Camera
from app.models.camera_groups import CameraGroup
from app.models.work_schedule import WorkSchedule
from app.models.events import Event
from app.models.alerts import Alert
from app.database import engine
from app.schemas.camera_schema import (
    CameraCreate,
    CameraRead,
    CameraActiveUpdate,
    CameraMapData,
    CameraStaffingSchedule,
)
from app.utils.security_utils import crypter, decrypter

# AJOUT : Import des middlewares de sécurité
from app.middleware.auth_middleware import (
    get_current_active_user,
    require_viewer,
    require_user,
    can_manage_cameras
)
from app.models.users import User

router = APIRouter()


def get_session():
    """Dépendance pour obtenir une session de base de données"""
    with Session(engine) as session:
        yield session


def _staffing_schedules_for(session: Session, cameras: List[Camera]) -> dict:
    """Résout en une requête les régimes actifs utilisés par les caméras."""
    ids = {
        camera.staffing_work_schedule_id for camera in cameras
        if camera.staffing_work_schedule_id is not None
    }
    if not ids:
        return {}
    rows = session.exec(
        select(WorkSchedule).where(
            WorkSchedule.id.in_(ids), WorkSchedule.is_active == True  # noqa: E712
        )
    ).all()
    return {schedule.id: schedule for schedule in rows}


def _validate_staffing_assignment(session: Session, camera_data: CameraCreate) -> None:
    """Un effectif surveillé exige un régime existant et actif."""
    if camera_data.staffing_min_agents is None:
        return
    schedule = session.get(WorkSchedule, camera_data.staffing_work_schedule_id)
    if not schedule:
        raise HTTPException(status_code=404, detail="Régime horaire d'effectif non trouvé.")
    if not schedule.is_active:
        raise HTTPException(
            status_code=409,
            detail="Le régime horaire d'effectif est désactivé.",
        )


def _to_camera_read(cam: Camera, staffing_schedule: Optional[WorkSchedule] = None) -> CameraRead:
    """Sérialise une caméra ORM en CameraRead : décryptage rtsp_url et
    appartenance aux groupes.

    `cam.groups` doit être chargé (lazy en session, ou eager via selectinload).
    """
    return CameraRead(
        id=cam.id,
        cam_name=cam.cam_name,
        # decrypter() renvoie None si rtsp_url est NULL (cas HikCentral).
        rtsp_url=decrypter(cam.rtsp_url),
        location=cam.location,
        is_active=cam.is_active,
        source_type=cam.source_type,
        hik_status=cam.hik_status,
        latitude=cam.latitude,
        longitude=cam.longitude,
        bearing=cam.bearing,
        staffing_max_agents=cam.staffing_max_agents,
        staffing_min_agents=cam.staffing_min_agents,
        staffing_tolerance_s=cam.staffing_tolerance_s,
        staffing_work_schedule_id=cam.staffing_work_schedule_id,
        staffing_schedule=(
            CameraStaffingSchedule(
                id=staffing_schedule.id,
                name=staffing_schedule.name,
                timezone=staffing_schedule.timezone,
                segments=staffing_schedule.segments,
            ) if staffing_schedule else None
        ),
        group_ids=[g.id for g in cam.groups],
        created_at=cam.created_at,
    )


# ─────────────────────────────────────────────
# CREATE CAMERA (Protégé - USER ou ADMIN)
# ─────────────────────────────────────────────

@router.post("/add")
def add_camera(
    camera: CameraCreate,
    current_user: User = Depends(can_manage_cameras),  # ← Protection ajoutée
    session: Session = Depends(get_session)
):
    """
    Ajoute une nouvelle caméra.
    
    Permissions requises : USER ou ADMIN
    """
    cam_name = camera.cam_name
    rtsp_url = camera.rtsp_url
    location = camera.location
    is_active = camera.is_active

    _validate_staffing_assignment(session, camera)

    if not cam_name or not rtsp_url:
        raise HTTPException(
            status_code=400,
            detail="Le nom et l'URL de la caméra sont obligatoires."
        )

    new_camera = Camera(
        cam_name=cam_name,
        rtsp_url=crypter(rtsp_url),
        location=location,
        is_active=is_active,
        latitude=camera.latitude,
        longitude=camera.longitude,
        bearing=camera.bearing if camera.bearing is not None else 0.0,
        staffing_max_agents=camera.staffing_max_agents,
        staffing_min_agents=camera.staffing_min_agents,
        staffing_tolerance_s=camera.staffing_tolerance_s,
        staffing_work_schedule_id=camera.staffing_work_schedule_id,
    )

    session.add(new_camera)
    session.commit()
    session.refresh(new_camera)

    return {
        "message": "Caméra ajoutée avec succès !",
        "camera_id": new_camera.id,
        "added_by": current_user.email  # ← Traçabilité
    }


# ─────────────────────────────────────────────
# READ ALL CAMERAS (Protégé - Tous les rôles)
# ─────────────────────────────────────────────
@router.get("/", response_model=List[CameraRead])
def get_cameras(
    group_id: Optional[int] = Query(
        default=None,
        description="Filtre : ne renvoyer que les caméras membres de ce groupe.",
    ),
    current_user: User = Depends(require_viewer),  # Protection ajoutée
    session: Session = Depends(get_session)
):
    """
    Liste les caméras avec appartenance aux groupes, géo-coordonnées et config
    EFFECTIVE des modules (ce que le Core lit pour (dé)activer le pipeline à chaud).

    Filtre optionnel `?group_id={id}` : ne renvoie que les caméras de ce groupe.

    Permissions requises : VIEWER, USER ou ADMIN
    """
    # selectinload(Camera.groups) : charge les groupes en 1 requête → évite le N+1
    # au calcul de la config effective.
    stmt = select(Camera).options(selectinload(Camera.groups))
    if group_id is not None:
        # Restreint aux caméras liées au groupe demandé (jointure sur la N↔N).
        stmt = stmt.where(Camera.groups.any(CameraGroup.id == group_id))
    cameras = session.exec(stmt).all()

    staffing_schedules = _staffing_schedules_for(session, cameras)
    return [
        _to_camera_read(cam, staffing_schedules.get(cam.staffing_work_schedule_id))
        for cam in cameras
    ]


# ─────────────────────────────────────────────
# MAP DATA (Protégé - Tous les rôles)
#
# ⚠ DÉCLARÉ AVANT /{camera_id} : sinon FastAPI tenterait de parser « map-data »
#   comme un entier camera_id (→ 422). L'ordre de déclaration prime.
# ─────────────────────────────────────────────

@router.get("/map-data", response_model=List[CameraMapData])
def get_cameras_map_data(
    current_user: User = Depends(require_viewer),
    session: Session = Depends(get_session)
):
    """
    Flux allégé pour le composant carte OpenStreetMap / Leaflet.

    Ne renvoie QUE les caméras ACTIVES ET géolocalisées (latitude/longitude non
    nuls), avec le strict nécessaire à l'affichage : id, name, latitude,
    longitude, bearing et la liste des modules effectivement actifs. Aucune
    rtsp_url ni secret n'est exposé.

    Permissions requises : VIEWER, USER ou ADMIN
    """
    stmt = (
        select(Camera)
        .where(Camera.is_active == True)  # noqa: E712 (SQLAlchemy exige == True)
        .where(Camera.latitude.is_not(None))
        .where(Camera.longitude.is_not(None))
        .options(selectinload(Camera.groups))
    )
    cameras = session.exec(stmt).all()

    out: List[CameraMapData] = []
    for cam in cameras:
        out.append(CameraMapData(
            id=cam.id,
            name=cam.cam_name,
            latitude=cam.latitude,
            longitude=cam.longitude,
            bearing=cam.bearing if cam.bearing is not None else 0.0,
        ))
    return out


# ─────────────────────────────────────────────
# READ CAMERA BY ID (Protégé - Tous les rôles)
# ─────────────────────────────────────────────

@router.get("/{camera_id}", response_model=CameraRead)
def get_camera(
    camera_id: int,
    current_user: User = Depends(require_viewer),  # ← Protection ajoutée
    session: Session = Depends(get_session)
):
    """
    Récupère une caméra par son ID (avec groupes, géo et config effective).

    Permissions requises : VIEWER, USER ou ADMIN
    """
    camera = session.get(Camera, camera_id)
    if not camera:
        raise HTTPException(status_code=404, detail="Caméra non trouvée")
    schedules = _staffing_schedules_for(session, [camera])
    return _to_camera_read(camera, schedules.get(camera.staffing_work_schedule_id))


# ─────────────────────────────────────────────
# UPDATE CAMERA (Protégé - USER ou ADMIN)
# ─────────────────────────────────────────────

@router.put("/update/{camera_id}", response_model=CameraRead)
def update_camera(
    camera_id: int,
    camera_data: CameraCreate,
    current_user: User = Depends(can_manage_cameras),  # ← Protection ajoutée
    session: Session = Depends(get_session)
):
    """
    Met à jour une caméra.
    
    Permissions requises : USER ou ADMIN
    """
    camera = session.get(Camera, camera_id)
    if not camera:
        raise HTTPException(status_code=404, detail="Caméra non trouvée")

    _validate_staffing_assignment(session, camera_data)

    camera.cam_name = camera_data.cam_name
    if camera.source_type == "hikcentral":
        # Le flux d'une caméra HikCentral est résolu dynamiquement. Une édition
        # de ses seuils d'effectif ne doit ni exiger ni créer une URL RTSP.
        pass
    elif camera_data.rtsp_url:
        camera.rtsp_url = crypter(camera_data.rtsp_url)
    else:
        raise HTTPException(
            status_code=400,
            detail="L'URL RTSP est obligatoire pour une caméra manuelle.",
        )
    camera.location = camera_data.location
    camera.is_active = camera_data.is_active
    camera.latitude = camera_data.latitude
    camera.longitude = camera_data.longitude
    if camera_data.bearing is not None:
        camera.bearing = camera_data.bearing
    camera.staffing_max_agents = camera_data.staffing_max_agents
    camera.staffing_min_agents = camera_data.staffing_min_agents
    camera.staffing_tolerance_s = camera_data.staffing_tolerance_s
    camera.staffing_work_schedule_id = camera_data.staffing_work_schedule_id

    session.add(camera)
    session.commit()
    session.refresh(camera)

    schedules = _staffing_schedules_for(session, [camera])
    return _to_camera_read(camera, schedules.get(camera.staffing_work_schedule_id))


# ─────────────────────────────────────────────
# (DÉS)ACTIVATION CAMÉRA (Protégé - USER ou ADMIN)
# ─────────────────────────────────────────────

@router.patch("/{camera_id}/active", response_model=CameraRead)
def set_camera_active(
    camera_id: int,
    payload: CameraActiveUpdate,
    current_user: User = Depends(can_manage_cameras),
    session: Session = Depends(get_session)
):
    """
    Active ou désactive une caméra (toggle léger : ne touche QUE is_active).

    C'est le mécanisme RECOMMANDÉ pour retirer une caméra du système sans perdre
    son historique : le Core (supervision) arrête ses threads et la synchro
    MediaMTX supprime son chemin automatiquement au cycle suivant. Réversible.

    Permissions requises : USER ou ADMIN
    """
    camera = session.get(Camera, camera_id)
    if not camera:
        raise HTTPException(status_code=404, detail="Caméra non trouvée")

    camera.is_active = payload.is_active
    session.add(camera)
    session.commit()
    session.refresh(camera)

    # Décrypte la rtsp_url + expose groupes/géo/config effective (cohérent avec
    # GET /cameras/).
    schedules = _staffing_schedules_for(session, [camera])
    return _to_camera_read(camera, schedules.get(camera.staffing_work_schedule_id))


# ─────────────────────────────────────────────
# DELETE CAMERA (Protégé - USER ou ADMIN)
# ─────────────────────────────────────────────

@router.delete("/delete/{camera_id}")
def delete_camera(
    camera_id: int,
    force: bool = False,
    current_user: User = Depends(can_manage_cameras),  # ← Protection ajoutée
    session: Session = Depends(get_session)
):
    """
    Supprime une caméra.

    Une caméra référencée par des événements ne peut pas être supprimée
    directement (FK non-nullable event.camera_id → l'ancien comportement plantait
    en 500). Désormais :
      - sans `force` : si des événements existent, renvoie un 409 explicite
        invitant à DÉSACTIVER la caméra (recommandé, préserve l'historique) ;
      - avec `force=true` : supprime EN CASCADE, dans l'ordre des contraintes FK,
        les alertes liées → les événements → la caméra (historique perdu).

    Permissions requises : USER ou ADMIN
    """
    camera = session.get(Camera, camera_id)
    if not camera:
        raise HTTPException(status_code=404, detail="Caméra non trouvée")

    # Événements rattachés (event.camera_id est un FK NON-nullable).
    event_ids = session.exec(select(Event.id).where(Event.camera_id == camera_id)).all()
    n_events = len(event_ids)

    if n_events > 0 and not force:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Cette caméra est référencée par {n_events} événement(s). "
                "Désactivez-la (recommandé, conserve l'historique) ou relancez la "
                "suppression avec force=true pour supprimer aussi ces événements et "
                "leurs alertes."
            ),
        )

    try:
        if n_events > 0:
            # Ordre imposé par les FK : alertes (alert.event_id) → événements → caméra.
            session.execute(sa_delete(Alert).where(Alert.event_id.in_(event_ids)))
            session.execute(sa_delete(Event).where(Event.camera_id == camera_id))
        session.delete(camera)
        session.commit()
    except Exception:
        session.rollback()
        raise HTTPException(status_code=500, detail="Échec de la suppression de la caméra.")

    return {
        "message": f"Caméra {camera_id} supprimée avec succès !",
        "deleted_events": n_events,
        "deleted_by": current_user.email  # ← Traçabilité
    }

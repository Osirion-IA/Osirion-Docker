from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from sqlmodel import Session, select
from app.database import get_session
from app.models.events import Event
from app.models.cameras import Camera
from app.schemas.events_schema import EventRead
from app.services.saveImage_service import save_image_from_bytes, is_valid_image_format
from app.middleware.auth_middleware import get_current_active_user, require_viewer
from typing import List, Optional
from datetime import datetime, timedelta
from sqlalchemy import and_, func, or_
import json
import logging

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/add", response_model=EventRead)
async def add_event(
    camera_id: int = Form(...),
    event_type: str = Form(...),
    confidence: Optional[float] = Form(None),
    meta: Optional[str] = Form(None),
    image: UploadFile = File(None),
    session: Session = Depends(get_session),
    _current_user=Depends(get_current_active_user)
):
    # meta arrive en chaîne JSON (multipart) → dict, best-effort (jamais bloquant).
    meta_obj = None
    if meta:
        try:
            meta_obj = json.loads(meta)
        except (ValueError, TypeError):
            meta_obj = None

    # Idempotence des événements critiques réessayés par le Core. La recherche ne
    # s'applique qu'aux rares événements portant event_uid ; le flux courant ne
    # paie aucun coût supplémentaire. On déduplique AVANT de sauvegarder l'image.
    event_uid = (meta_obj or {}).get("event_uid")
    if event_uid:
        existing = session.exec(
            select(Event).where(
                Event.camera_id == camera_id,
                Event.event_type == event_type,
                Event.meta["event_uid"].as_string() == str(event_uid),
            )
        ).first()
        if existing:
            return existing

    snapshot_url = None
    if image:
        if not is_valid_image_format(image):
            raise HTTPException(status_code=400, detail="Format d'image non supporté.")

        image_bytes = await image.read()
        snapshot_url = await save_image_from_bytes(
            image_bytes=image_bytes,
            content_type=image.content_type,
            save_path="snapshots/"
        )

    new_event = Event(
        camera_id=camera_id,
        event_type=event_type,
        confidence=confidence,
        snapshot_url=snapshot_url,
        meta=meta_obj,
    )

    session.add(new_event)
    session.commit()
    session.refresh(new_event)

    # Moteur de décision : évalue les règles actives (best-effort, ne bloque jamais
    # l'enregistrement de l'événement).
    try:
        from app.services.rule_engine import evaluate_event
        evaluate_event(session, new_event)
    except Exception:
        logger.warning("[events] évaluation des règles ignorée (erreur non bloquante)", exc_info=True)

    return new_event


@router.get("/", response_model=List[EventRead])
async def get_all_events(
    session: Session = Depends(get_session),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    event_types: Optional[str] = Query(
        None, description="Types séparés par des virgules.",
    ),
    camera_id: Optional[int] = Query(None, ge=1),
    with_snapshot: Optional[bool] = Query(None),
    _current_user=Depends(require_viewer)
):
    statement = select(Event)
    if event_types:
        types = {value.strip() for value in event_types.split(",") if value.strip()}
        if types:
            statement = statement.where(Event.event_type.in_(types))
    if camera_id is not None:
        statement = statement.where(Event.camera_id == camera_id)
    if with_snapshot is True:
        statement = statement.where(Event.snapshot_url.is_not(None))
    elif with_snapshot is False:
        statement = statement.where(Event.snapshot_url.is_(None))
    statement = statement.offset(skip).limit(limit).order_by(Event.id.desc())
    return session.exec(statement).all()


PRESENCE_EVENT_TYPES = {
    "POST_VACANT",
    "POST_ABSENCE",
    "STAFFING_LOW",
    "STAFFING_RECOVERED",
}


@router.get("/presence-history")
async def get_presence_history(
    session: Session = Depends(get_session),
    days: int = Query(30, ge=1, le=365),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=5, le=100),
    event_type: Optional[str] = Query(None),
    camera_id: Optional[int] = Query(None, ge=1),
    work_schedule_id: Optional[int] = Query(None, ge=1),
    search: Optional[str] = Query(None, max_length=100),
    include_archived: bool = Query(False),
    _current_user=Depends(require_viewer),
):
    """Historique métier paginé du module Présence des agents.

    Contrairement au journal technique général, ce flux applique réellement la
    période sélectionnée, conserve le contexte caméra/groupe et renvoie un total
    fiable pour la pagination. Les anciennes clôtures sans capture réutilisent
    visuellement la preuve du début de leur épisode, sans modifier l'historique.
    """
    since = datetime.utcnow() - timedelta(days=days)
    scope_filters = [
        Event.event_type.in_(PRESENCE_EVENT_TYPES),
        Event.timestamp >= since,
    ]
    if camera_id is not None:
        scope_filters.append(Event.camera_id == camera_id)
    if work_schedule_id is not None:
        scope_filters.append(
            Event.meta["schedule_id"].as_integer() == work_schedule_id
        )
    cleaned_search = (search or "").strip()
    if cleaned_search:
        pattern = f"%{cleaned_search}%"
        scope_filters.append(or_(
            Camera.cam_name.ilike(pattern),
            Camera.location.ilike(pattern),
            Event.meta["zone_name"].as_string().ilike(pattern),
            Event.meta["schedule_name"].as_string().ilike(pattern),
        ))

    quality = Event.meta["presence_data_quality"].as_string()
    reliable_presence = or_(
        Event.event_type.in_(("STAFFING_LOW", "STAFFING_RECOVERED")),
        quality == "reliable",
        and_(
            quality.is_(None),
            or_(
                and_(
                    Event.event_type == "POST_VACANT",
                    Event.meta["decision"].as_string().is_not(None),
                ),
                and_(
                    Event.event_type == "POST_ABSENCE",
                    Event.meta["resolution_reason"].as_string().is_not(None),
                ),
            ),
        ),
    )
    base_filters = list(scope_filters)
    if not include_archived:
        base_filters.append(reliable_presence)

    item_filters = list(base_filters)
    if event_type:
        if event_type not in PRESENCE_EVENT_TYPES:
            raise HTTPException(status_code=422, detail="Type d'événement de présence invalide.")
        item_filters.append(Event.event_type == event_type)

    join_condition = Event.camera_id == Camera.id
    archived_total = session.exec(
        select(func.count(Event.id))
        .select_from(Event)
        .join(Camera, join_condition)
        .where(
            *scope_filters,
            Event.event_type.in_(("POST_VACANT", "POST_ABSENCE")),
            quality == "archived",
        )
    ).one()
    total = session.exec(
        select(func.count(Event.id))
        .select_from(Event)
        .join(Camera, join_condition)
        .where(*item_filters)
    ).one()
    rows = session.exec(
        select(Event, Camera)
        .join(Camera, join_condition)
        .where(*item_filters)
        .order_by(Event.timestamp.desc(), Event.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    # Les compteurs restent globaux dans le périmètre période/caméra/groupe : ils
    # servent de filtres rapides même lorsqu'un type précis est sélectionné.
    summary_rows = session.exec(
        select(Event.event_type, func.count(Event.id))
        .select_from(Event)
        .join(Camera, join_condition)
        .where(*base_filters)
        .group_by(Event.event_type)
    ).all()
    summary = {kind: 0 for kind in PRESENCE_EVENT_TYPES}
    summary.update({kind: int(count) for kind, count in summary_rows})

    # Résout les captures des anciens POST_ABSENCE qui précèdent l'ajout d'une
    # frame de clôture. Le chemin n'est pas recopié en base : le fichier garde un
    # propriétaire unique et la maintenance ne peut pas le supprimer par erreur.
    closure_episode_ids = {
        str((event.meta or {}).get("episode_id"))
        for event, _camera in rows
        if event.event_type == "POST_ABSENCE"
        and not event.snapshot_url
        and (event.meta or {}).get("episode_id")
    }
    opening_snapshots = {}
    if closure_episode_ids:
        openings = session.exec(
            select(Event).where(
                Event.event_type == "POST_VACANT",
                Event.meta["episode_id"].as_string().in_(closure_episode_ids),
                Event.snapshot_url.is_not(None),
            )
        ).all()
        opening_snapshots = {
            str((event.meta or {}).get("episode_id")): event.snapshot_url
            for event in openings
        }

    items = []
    for event, camera in rows:
        episode_id = str((event.meta or {}).get("episode_id") or "")
        fallback_snapshot = opening_snapshots.get(episode_id)
        items.append({
            "id": event.id,
            "camera_id": event.camera_id,
            "camera_nom": camera.cam_name,
            "camera_location": camera.location,
            "event_type": event.event_type,
            "confidence": event.confidence,
            "snapshot_url": event.snapshot_url or fallback_snapshot,
            "snapshot_fallback": "vacancy_event" if fallback_snapshot else None,
            "data_quality": (
                (event.meta or {}).get("presence_data_quality")
                or ("reliable" if event.event_type in ("STAFFING_LOW", "STAFFING_RECOVERED") else None)
            ),
            "meta": event.meta,
            "timestamp": event.timestamp,
        })

    return {
        "items": items,
        "total": int(total),
        "page": page,
        "page_size": page_size,
        "pages": max(1, (int(total) + page_size - 1) // page_size),
        "days": days,
        "summary": summary,
        "include_archived": include_archived,
        "archived_total": int(archived_total),
    }


@router.get("/{event_id}", response_model=EventRead)
async def get_event_by_id(
    event_id: int,
    session: Session = Depends(get_session),
    _current_user=Depends(require_viewer)
):
    event = session.get(Event, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Événement non trouvé.")
    return event

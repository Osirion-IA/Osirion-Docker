from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlmodel import Session, select
from app.database import get_session
from app.models.events import Event
from app.models.alerts import Alert, ALERT_KIND_PERSON
from app.models.people import People
from app.schemas.events_schema import EventRead
from app.services.saveImage_service import save_image_from_bytes, is_valid_image_format
from app.middleware.auth_middleware import get_current_active_user, require_viewer
from typing import List, Optional
import logging

router = APIRouter()
logger = logging.getLogger(__name__)


def _maybe_create_alert(session: Session, event: Event) -> None:
    """Crée une alerte SI l'événement concerne une entité blacklistée.

    Appelé en best-effort après la création d'un événement : ne lève jamais vers
    l'appelant (l'enregistrement de l'événement ne doit jamais échouer à cause de
    l'alerte). N'envoie AUCUNE notification — ce n'est qu'un enregistrement.
    """
    kind = label = reason = None
    person_id = None

    if event.person_id:
        person = session.get(People, event.person_id)
        if person and getattr(person, "is_blacklisted", False):
            kind = ALERT_KIND_PERSON
            label = f"{person.first_name} {person.last_name}"
            reason = getattr(person, "blacklist_reason", None)
            person_id = person.id

    if kind is None:
        return  # rien à signaler

    session.add(Alert(
        event_id=event.id, kind=kind, label=label or "—", reason=reason,
        camera_id=event.camera_id, person_id=person_id,
        snapshot_url=event.snapshot_url,
    ))
    session.commit()
    logger.info(f"[alert] créée : kind={kind} label={label!r} (event_id={event.id})")


@router.post("/add", response_model=EventRead)
async def add_event(
    camera_id: int = Form(...),
    person_id: Optional[int] = Form(None),
    event_type: str = Form(...),
    confidence: Optional[float] = Form(None),
    image: UploadFile = File(None),
    session: Session = Depends(get_session),
    _current_user=Depends(get_current_active_user)
):
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
        person_id=person_id,
        event_type=event_type,
        confidence=confidence,
        snapshot_url=snapshot_url,
    )

    session.add(new_event)
    session.commit()
    session.refresh(new_event)

    # Best-effort : crée une alerte si blacklist. Ne bloque jamais l'événement.
    try:
        _maybe_create_alert(session, new_event)
    except Exception:
        logger.warning("[events] création d'alerte ignorée (erreur non bloquante)", exc_info=True)

    return new_event


@router.get("/", response_model=List[EventRead])
async def get_all_events(
    session: Session = Depends(get_session),
    skip: int = 0,
    limit: int = 100,
    _current_user=Depends(require_viewer)
):
    statement = select(Event).offset(skip).limit(limit).order_by(Event.id.desc())
    return session.exec(statement).all()


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

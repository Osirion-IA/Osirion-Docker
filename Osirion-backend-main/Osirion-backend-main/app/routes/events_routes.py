from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlmodel import Session, select
from app.database import get_session
from app.models.events import Event
from app.schemas.events_schema import EventRead
from app.services.saveImage_service import save_image_from_bytes, is_valid_image_format
from app.middleware.auth_middleware import get_current_active_user, require_viewer
from typing import List, Optional

router = APIRouter()


@router.post("/add", response_model=EventRead)
async def add_event(
    camera_id: int = Form(...),
    person_id: Optional[int] = Form(None),
    event_type: str = Form(...),
    confidence: Optional[float] = Form(None),
    plate_text_detected: Optional[str] = Form(None),
    vehicle_id: Optional[int] = Form(None),
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
        plate_text_detected=plate_text_detected,
        vehicle_id=vehicle_id
    )

    session.add(new_event)
    session.commit()
    session.refresh(new_event)

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

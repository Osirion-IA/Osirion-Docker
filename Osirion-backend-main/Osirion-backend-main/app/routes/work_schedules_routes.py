# app/routes/work_schedules_routes.py
"""
CRUD des RÉGIMES HORAIRES (jours, créneaux, fuseau, tolérance d'absence).

Un régime est partagé par N zones de présence : le modifier se répercute sur
toutes les caméras concernées au prochain rafraîchissement du Core
(ZONES_REFRESH_SECONDS, 30 s par défaut) — un réglage, tout un pays.

Lecture : VIEWER+ ; écriture : USER/ADMIN, comme les zones et les caméras.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from typing import List, Optional
from datetime import datetime

from app.database import get_session
from app.models.work_schedule import WorkSchedule
from app.models.zones import Zone
from app.models.users import User
from app.schemas.work_schedule_schema import (
    WorkScheduleCreate, WorkScheduleUpdate, WorkScheduleRead,
)
from app.middleware.auth_middleware import require_viewer, can_manage_cameras

router = APIRouter()


def _counts(session: Session) -> dict:
    """{work_schedule_id: nb de zones}, en UNE requête (pas de N+1 sur la liste)."""
    rows = session.exec(
        select(Zone.work_schedule_id, func.count(Zone.id))
        .where(Zone.work_schedule_id.is_not(None))
        .group_by(Zone.work_schedule_id)
    ).all()
    return {sid: n for sid, n in rows}


def _read(s: WorkSchedule, zones_count: int = 0) -> WorkScheduleRead:
    return WorkScheduleRead(**s.model_dump(), zones_count=zones_count)


def _or_404(session: Session, schedule_id: int) -> WorkSchedule:
    s = session.get(WorkSchedule, schedule_id)
    if not s:
        raise HTTPException(status_code=404, detail="Régime horaire non trouvé.")
    return s


@router.get("/", response_model=List[WorkScheduleRead])
def list_schedules(
    active_only: bool = Query(False, description="Ne renvoyer que les régimes actifs."),
    _user: User = Depends(require_viewer),
    session: Session = Depends(get_session),
):
    stmt = select(WorkSchedule)
    if active_only:
        stmt = stmt.where(WorkSchedule.is_active == True)  # noqa: E712
    counts = _counts(session)
    return [_read(s, counts.get(s.id, 0)) for s in session.exec(stmt.order_by(WorkSchedule.name)).all()]


@router.post("/add", response_model=WorkScheduleRead, status_code=201)
def add_schedule(
    payload: WorkScheduleCreate,
    _user: User = Depends(can_manage_cameras),
    session: Session = Depends(get_session),
):
    if session.exec(select(WorkSchedule).where(WorkSchedule.name == payload.name)).first():
        raise HTTPException(status_code=409, detail="Un régime porte déjà ce nom.")
    schedule = WorkSchedule(**payload.model_dump())
    session.add(schedule)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(status_code=409, detail="Un régime porte déjà ce nom.")
    session.refresh(schedule)
    return _read(schedule, 0)


@router.put("/{schedule_id}", response_model=WorkScheduleRead)
def update_schedule(
    schedule_id: int,
    payload: WorkScheduleUpdate,
    _user: User = Depends(can_manage_cameras),
    session: Session = Depends(get_session),
):
    schedule = _or_404(session, schedule_id)
    data = payload.model_dump(exclude_unset=True)
    nom = data.get("name")
    if nom and nom != schedule.name:
        doublon = session.exec(select(WorkSchedule).where(WorkSchedule.name == nom)).first()
        if doublon:
            raise HTTPException(status_code=409, detail="Un régime porte déjà ce nom.")
    for key, value in data.items():
        setattr(schedule, key, value)
    schedule.updated_at = datetime.utcnow()
    session.add(schedule)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(status_code=409, detail="Un régime porte déjà ce nom.")
    session.refresh(schedule)
    return _read(schedule, _counts(session).get(schedule.id, 0))


@router.delete("/{schedule_id}")
def delete_schedule(
    schedule_id: int,
    force: bool = Query(False, description="Supprimer même si des zones l'utilisent."),
    _user: User = Depends(can_manage_cameras),
    session: Session = Depends(get_session),
):
    """Supprime un régime.

    Sans `force`, un régime encore utilisé est REFUSÉ (409) : le supprimer
    laisserait ses zones sans horaires (FK ON DELETE SET NULL), donc silencieusement
    non surveillées. Mieux vaut l'annoncer que de le découvrir des semaines plus tard.
    """
    schedule = _or_404(session, schedule_id)
    n = _counts(session).get(schedule_id, 0)
    if n and not force:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Ce régime est utilisé par {n} zone(s) de présence. Réaffectez-les à "
                "un autre régime, ou relancez avec force=true — ces postes cesseraient "
                "alors d'être surveillés."
            ),
        )
    session.delete(schedule)
    session.commit()
    return {"message": f"Régime {schedule_id} supprimé.", "zones_orphelines": n}

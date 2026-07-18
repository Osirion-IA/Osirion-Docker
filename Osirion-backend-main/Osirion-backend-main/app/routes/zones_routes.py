# app/routes/zones_routes.py
"""
CRUD des primitives spatiales par caméra : zones (polygones) et lignes de comptage.
Lecture : VIEWER+ ; écriture : USER/ADMIN (comme les caméras). Consommées par
l'Event Engine (Phase C) pour occupation, files, attroupement et comptage E/S.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select
from typing import List, Optional
from datetime import datetime

from app.database import get_session
from app.models.zones import Zone, CountLine
from app.models.cameras import Camera
from app.models.users import User
from app.schemas.zones_schema import (
    ZoneCreate, ZoneUpdate, ZoneRead,
    CountLineCreate, CountLineUpdate, CountLineRead,
)
from app.middleware.auth_middleware import require_viewer, can_manage_cameras

router = APIRouter()


def _camera_or_404(session: Session, camera_id: int) -> None:
    if not session.get(Camera, camera_id):
        raise HTTPException(status_code=404, detail="Caméra non trouvée.")


# ─────────────────────────────────────────────
# ZONES (polygones)
# ─────────────────────────────────────────────
@router.get("/", response_model=List[ZoneRead])
def list_zones(
    camera_id: Optional[int] = Query(None, description="Filtre par caméra."),
    _user: User = Depends(require_viewer),
    session: Session = Depends(get_session),
):
    stmt = select(Zone)
    if camera_id is not None:
        stmt = stmt.where(Zone.camera_id == camera_id)
    return session.exec(stmt).all()


@router.post("/add", response_model=ZoneRead, status_code=201)
def add_zone(
    payload: ZoneCreate,
    _user: User = Depends(can_manage_cameras),
    session: Session = Depends(get_session),
):
    _camera_or_404(session, payload.camera_id)
    zone = Zone(**payload.model_dump())
    session.add(zone)
    session.commit()
    session.refresh(zone)
    return zone


@router.put("/{zone_id}", response_model=ZoneRead)
def update_zone(
    zone_id: int,
    payload: ZoneUpdate,
    _user: User = Depends(can_manage_cameras),
    session: Session = Depends(get_session),
):
    zone = session.get(Zone, zone_id)
    if not zone:
        raise HTTPException(status_code=404, detail="Zone non trouvée.")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(zone, key, value)
    zone.updated_at = datetime.utcnow()
    session.add(zone)
    session.commit()
    session.refresh(zone)
    return zone


@router.delete("/{zone_id}")
def delete_zone(
    zone_id: int,
    _user: User = Depends(can_manage_cameras),
    session: Session = Depends(get_session),
):
    zone = session.get(Zone, zone_id)
    if not zone:
        raise HTTPException(status_code=404, detail="Zone non trouvée.")
    session.delete(zone)
    session.commit()
    return {"message": f"Zone {zone_id} supprimée."}


# ─────────────────────────────────────────────
# LIGNES DE COMPTAGE (segments)
#   ⚠ Déclarées AVANT /{zone_id} n'est pas nécessaire (préfixe /lines littéral),
#   mais on garde les routes lignes groupées et explicites.
# ─────────────────────────────────────────────
@router.get("/lines", response_model=List[CountLineRead])
def list_lines(
    camera_id: Optional[int] = Query(None, description="Filtre par caméra."),
    _user: User = Depends(require_viewer),
    session: Session = Depends(get_session),
):
    stmt = select(CountLine)
    if camera_id is not None:
        stmt = stmt.where(CountLine.camera_id == camera_id)
    return session.exec(stmt).all()


@router.post("/lines/add", response_model=CountLineRead, status_code=201)
def add_line(
    payload: CountLineCreate,
    _user: User = Depends(can_manage_cameras),
    session: Session = Depends(get_session),
):
    _camera_or_404(session, payload.camera_id)
    line = CountLine(**payload.model_dump())
    session.add(line)
    session.commit()
    session.refresh(line)
    return line


@router.put("/lines/{line_id}", response_model=CountLineRead)
def update_line(
    line_id: int,
    payload: CountLineUpdate,
    _user: User = Depends(can_manage_cameras),
    session: Session = Depends(get_session),
):
    line = session.get(CountLine, line_id)
    if not line:
        raise HTTPException(status_code=404, detail="Ligne de comptage non trouvée.")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(line, key, value)
    line.updated_at = datetime.utcnow()
    session.add(line)
    session.commit()
    session.refresh(line)
    return line


@router.delete("/lines/{line_id}")
def delete_line(
    line_id: int,
    _user: User = Depends(can_manage_cameras),
    session: Session = Depends(get_session),
):
    line = session.get(CountLine, line_id)
    if not line:
        raise HTTPException(status_code=404, detail="Ligne de comptage non trouvée.")
    session.delete(line)
    session.commit()
    return {"message": f"Ligne {line_id} supprimée."}

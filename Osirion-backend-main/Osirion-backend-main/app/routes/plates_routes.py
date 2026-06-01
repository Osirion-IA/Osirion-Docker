# app/routes/plates_routes.py
"""
Gestion des plaques d'immatriculation (LPR / ANPR).

Symétrique de people_routes.py (côté reconnaissance faciale) :
  - CRUD des véhicules connus / surveillés (table Vehicle)
  - Recherche FLOUE (fuzzy) d'une plaque lue par l'OCR, tolérante aux
    erreurs de lecture (O↔0, I↔1, S↔5…), au lieu d'une égalité SQL stricte.

Permissions (réutilise les RoleChecker existants) :
  - lecture / recherche : require_viewer (viewer, user, admin)
  - écriture (add/update/delete/blacklist) : require_user (user, admin)
"""
from fastapi import APIRouter, Depends, Request, HTTPException
from sqlmodel import Session, select
from datetime import datetime
from typing import List
import logging

from app.database import engine
from app.models.vehicles import Vehicle
from app.schemas.vehicles_schema import (
    VehicleCreate, VehicleUpdate, VehicleRead,
    PlateSearchRequest, PlateSearchResponse, PlateMatch,
)
from app.middleware.auth_middleware import require_viewer, require_user
from app.middleware.rate_limit import limiter
from app.utils.plate_utils import normalize_plate, plate_similarity

router = APIRouter()
logger = logging.getLogger(__name__)


def get_session():
    with Session(engine) as session:
        yield session


# ─────────────────────────────────────────────────────────────────────────────
# CREATE — enregistrer une plaque connue / surveillée  (USER ou ADMIN)
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/add", response_model=VehicleRead)
def add_vehicle(
    payload: VehicleCreate,
    _current_user=Depends(require_user),
    session: Session = Depends(get_session),
):
    normalized = normalize_plate(payload.plate_text)
    if not normalized:
        raise HTTPException(status_code=400, detail="Plaque vide ou invalide après normalisation.")

    existing = session.exec(
        select(Vehicle).where(Vehicle.plate_text == normalized)
    ).first()
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"La plaque {normalized} est déjà enregistrée (id={existing.id}).",
        )

    vehicle = Vehicle(
        plate_text=normalized,
        owner_name=payload.owner_name,
        is_blacklisted=payload.is_blacklisted,
        notes=payload.notes,
    )
    session.add(vehicle)
    session.commit()
    session.refresh(vehicle)

    logger.info(
        f"[plates] Véhicule ajouté : {normalized} "
        f"(blacklist={vehicle.is_blacklisted}, id={vehicle.id})"
    )
    return vehicle


# ─────────────────────────────────────────────────────────────────────────────
# READ — liste / détail  (tous rôles)
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/", response_model=List[VehicleRead])
def list_vehicles(
    skip: int = 0,
    limit: int = 100,
    blacklisted_only: bool = False,
    _current_user=Depends(require_viewer),
    session: Session = Depends(get_session),
):
    stmt = select(Vehicle)
    if blacklisted_only:
        stmt = stmt.where(Vehicle.is_blacklisted == True)  # noqa: E712
    stmt = stmt.offset(skip).limit(limit).order_by(Vehicle.id.desc())
    return session.exec(stmt).all()


@router.get("/{vehicle_id}", response_model=VehicleRead)
def get_vehicle(
    vehicle_id: int,
    _current_user=Depends(require_viewer),
    session: Session = Depends(get_session),
):
    vehicle = session.get(Vehicle, vehicle_id)
    if not vehicle:
        raise HTTPException(status_code=404, detail="Véhicule non trouvé.")
    return vehicle


# ─────────────────────────────────────────────────────────────────────────────
# UPDATE  (USER ou ADMIN)
# ─────────────────────────────────────────────────────────────────────────────

@router.put("/update/{vehicle_id}", response_model=VehicleRead)
def update_vehicle(
    vehicle_id: int,
    payload: VehicleUpdate,
    _current_user=Depends(require_user),
    session: Session = Depends(get_session),
):
    vehicle = session.get(Vehicle, vehicle_id)
    if not vehicle:
        raise HTTPException(status_code=404, detail="Véhicule non trouvé.")

    if payload.plate_text is not None:
        normalized = normalize_plate(payload.plate_text)
        if not normalized:
            raise HTTPException(status_code=400, detail="Plaque invalide après normalisation.")
        # Refuser un doublon sur une autre ligne
        clash = session.exec(
            select(Vehicle).where(
                Vehicle.plate_text == normalized,
                Vehicle.id != vehicle_id,
            )
        ).first()
        if clash:
            raise HTTPException(status_code=409, detail=f"Plaque {normalized} déjà utilisée (id={clash.id}).")
        vehicle.plate_text = normalized
    if payload.owner_name is not None:
        vehicle.owner_name = payload.owner_name
    if payload.is_blacklisted is not None:
        vehicle.is_blacklisted = payload.is_blacklisted
    if payload.notes is not None:
        vehicle.notes = payload.notes

    vehicle.updated_at = datetime.utcnow()
    session.add(vehicle)
    session.commit()
    session.refresh(vehicle)
    return vehicle


# ─────────────────────────────────────────────────────────────────────────────
# BLACKLIST — raccourci pour (dé)marquer un véhicule  (USER ou ADMIN)
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/blacklist/{vehicle_id}", response_model=VehicleRead)
def set_blacklist(
    vehicle_id: int,
    blacklisted: bool = True,
    _current_user=Depends(require_user),
    session: Session = Depends(get_session),
):
    vehicle = session.get(Vehicle, vehicle_id)
    if not vehicle:
        raise HTTPException(status_code=404, detail="Véhicule non trouvé.")
    vehicle.is_blacklisted = blacklisted
    vehicle.updated_at = datetime.utcnow()
    session.add(vehicle)
    session.commit()
    session.refresh(vehicle)
    logger.info(f"[plates] Véhicule id={vehicle_id} blacklist={blacklisted}")
    return vehicle


# ─────────────────────────────────────────────────────────────────────────────
# DELETE  (USER ou ADMIN)
# ─────────────────────────────────────────────────────────────────────────────

@router.delete("/delete/{vehicle_id}")
def delete_vehicle(
    vehicle_id: int,
    _current_user=Depends(require_user),
    session: Session = Depends(get_session),
):
    vehicle = session.get(Vehicle, vehicle_id)
    if not vehicle:
        raise HTTPException(status_code=404, detail="Véhicule non trouvé.")
    session.delete(vehicle)
    session.commit()
    return {"message": f"Véhicule {vehicle_id} supprimé avec succès."}


# ─────────────────────────────────────────────────────────────────────────────
# SEARCH — recherche FLOUE d'une plaque lue par l'OCR  (tous rôles)
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/search", response_model=PlateSearchResponse)
@limiter.limit("600/minute")
def search_plate(
    request: Request,
    req: PlateSearchRequest,
    _current_user=Depends(require_viewer),
    session: Session = Depends(get_session),
):
    """
    Recherche le(s) véhicule(s) dont la plaque ressemble le plus à `plate_text`.

    Algorithme :
      1. Normalisation de la requête.
      2. Tentative de correspondance EXACTE (rapide) → score 1.0.
      3. Sinon, similarité de Levenshtein normalisée (+ repliement OCR) contre
         toutes les plaques connues ; on garde les k meilleures ≥ threshold.
    """
    query = normalize_plate(req.plate_text)
    if not query:
        return PlateSearchResponse(query="", matched=False, results=[])

    vehicles = session.exec(
        select(Vehicle.id, Vehicle.plate_text, Vehicle.owner_name, Vehicle.is_blacklisted)
    ).all()

    scored: list[PlateMatch] = []
    for vid, plate, owner, blacklisted in vehicles:
        exact = (plate == query)
        score = 1.0 if exact else plate_similarity(query, plate)
        if score >= req.threshold:
            scored.append(PlateMatch(
                id=vid, plate_text=plate, owner_name=owner,
                is_blacklisted=blacklisted, score=round(score, 4), exact=exact,
            ))

    scored.sort(key=lambda m: m.score, reverse=True)
    top = scored[: max(1, req.k)]

    if top:
        best = top[0]
        logger.info(
            f"[plates/search] query={query!r} → match={best.plate_text!r} "
            f"score={best.score} blacklist={best.is_blacklisted} "
            f"(exact={best.exact}, candidats={len(scored)})"
        )
    else:
        logger.info(f"[plates/search] query={query!r} → aucune correspondance ≥ {req.threshold}")

    return PlateSearchResponse(query=query, matched=bool(top), results=top)

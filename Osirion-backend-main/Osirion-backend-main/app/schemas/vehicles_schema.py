# app/schemas/vehicles_schema.py
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class VehicleCreate(BaseModel):
    plate_text: str
    owner_name: Optional[str] = None
    is_blacklisted: bool = False
    notes: Optional[str] = None


class VehicleUpdate(BaseModel):
    plate_text: Optional[str] = None
    owner_name: Optional[str] = None
    is_blacklisted: Optional[bool] = None
    notes: Optional[str] = None


class VehicleRead(BaseModel):
    id: int
    plate_text: str
    owner_name: Optional[str]
    is_blacklisted: bool
    notes: Optional[str]
    created_at: datetime
    updated_at: Optional[datetime]


class PlateSearchRequest(BaseModel):
    plate_text: str            # texte brut lu par l'OCR (sera normalisé)
    threshold: float = 0.82    # similarité minimale pour accepter une correspondance
    k: int = 1                 # nombre de candidats à retourner


class PlateMatch(BaseModel):
    id: int
    plate_text: str
    owner_name: Optional[str]
    is_blacklisted: bool
    score: float               # similarité ∈ [0, 1]
    exact: bool                # True si correspondance exacte (après normalisation)


class PlateSearchResponse(BaseModel):
    query: str                 # plaque normalisée recherchée
    matched: bool              # au moins un candidat ≥ threshold
    results: List[PlateMatch]

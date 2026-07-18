# app/schemas/zones_schema.py
from pydantic import BaseModel, field_validator
from typing import Optional, List
from datetime import datetime

# Un point = [x, y] normalisé dans [0, 1].
Point = List[float]


def _valid_point(p) -> bool:
    return (
        isinstance(p, (list, tuple)) and len(p) == 2
        and all(isinstance(c, (int, float)) and 0.0 <= float(c) <= 1.0 for c in p)
    )


# ── Zones (polygones) ────────────────────────────────────────────────────────
class ZoneCreate(BaseModel):
    camera_id: int
    name: str
    kind: str = "generic"
    polygon: List[Point]
    color: Optional[str] = None

    @field_validator("polygon")
    @classmethod
    def _check_polygon(cls, v):
        if not isinstance(v, list) or len(v) < 3:
            raise ValueError("Un polygone exige au moins 3 points.")
        if not all(_valid_point(p) for p in v):
            raise ValueError("Chaque point doit être [x, y] normalisé dans [0, 1].")
        return v


class ZoneUpdate(BaseModel):
    name: Optional[str] = None
    kind: Optional[str] = None
    polygon: Optional[List[Point]] = None
    color: Optional[str] = None
    is_active: Optional[bool] = None

    @field_validator("polygon")
    @classmethod
    def _check_polygon(cls, v):
        if v is None:
            return v
        if len(v) < 3 or not all(_valid_point(p) for p in v):
            raise ValueError("Polygone invalide (≥ 3 points, chacun [x, y] dans [0, 1]).")
        return v


class ZoneRead(BaseModel):
    id: int
    camera_id: int
    name: str
    kind: str
    polygon: List[Point]
    color: Optional[str] = None
    is_active: bool
    created_at: datetime


# ── Lignes de comptage ───────────────────────────────────────────────────────
class CountLineCreate(BaseModel):
    camera_id: int
    name: str
    point_a: Point
    point_b: Point
    in_direction: str = "positive"

    @field_validator("point_a", "point_b")
    @classmethod
    def _check_point(cls, v):
        if not _valid_point(v):
            raise ValueError("Point invalide : attendu [x, y] normalisé dans [0, 1].")
        return v


class CountLineUpdate(BaseModel):
    name: Optional[str] = None
    point_a: Optional[Point] = None
    point_b: Optional[Point] = None
    in_direction: Optional[str] = None
    is_active: Optional[bool] = None

    @field_validator("point_a", "point_b")
    @classmethod
    def _check_point(cls, v):
        if v is None:
            return v
        if not _valid_point(v):
            raise ValueError("Point invalide : attendu [x, y] normalisé dans [0, 1].")
        return v


class CountLineRead(BaseModel):
    id: int
    camera_id: int
    name: str
    point_a: Point
    point_b: Point
    in_direction: str
    is_active: bool
    created_at: datetime

# core/geometry.py
"""
Géométrie 2D en coordonnées NORMALISÉES [0,1] — CPU pur, pour l'Event Engine.
Aucune dépendance lourde : ray-casting + produit vectoriel.
"""
from typing import Sequence


def point_in_polygon(x: float, y: float, poly: Sequence[Sequence[float]]) -> bool:
    """Test point-dans-polygone par ray-casting. `poly` = [[x,y], …] (≥ 3 points),
    coordonnées normalisées. Robuste aux polygones concaves."""
    n = len(poly)
    if n < 3:
        return False
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = poly[i][0], poly[i][1]
        xj, yj = poly[j][0], poly[j][1]
        denom = (yj - yi) or 1e-12
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / denom + xi):
            inside = not inside
        j = i
    return inside


def segment_side(ax: float, ay: float, bx: float, by: float,
                 px: float, py: float) -> float:
    """Signe du produit vectoriel AB × AP : > 0 d'un côté du segment, < 0 de
    l'autre, 0 sur la droite (AB). Sert à détecter le franchissement d'une ligne
    (changement de signe entre deux frames)."""
    return (bx - ax) * (py - ay) - (by - ay) * (px - ax)

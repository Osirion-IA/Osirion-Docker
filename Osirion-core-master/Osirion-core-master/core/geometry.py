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


def bbox_polygon_overlap_ratio(
    bbox: Sequence[float],
    poly: Sequence[Sequence[float]],
    samples: int = 7,
) -> float:
    """Part approximative d'une boîte incluse dans un polygone, dans ``[0, 1]``.

    ``bbox`` et ``poly`` sont en coordonnées image normalisées. L'échantillonnage
    régulier évite une dépendance géométrique lourde et reste robuste pour les
    polygones concaves dessinés dans l'UI. Sept points par axe (49 tests) donnent
    une précision largement suffisante pour décider si le CORPS d'une personne
    recouvre majoritairement une zone de poste.

    Cette primitive ne remplace pas le point au sol pour les files, intrusions et
    lignes : elle est destinée aux zones ``presence``, où les pieds sont souvent
    cachés par un comptoir ou coupés par le bord de l'image.
    """
    if len(bbox) != 4 or len(poly) < 3:
        return 0.0
    try:
        x1, y1, x2, y2 = (float(v) for v in bbox)
    except (TypeError, ValueError):
        return 0.0
    x1, x2 = sorted((max(0.0, min(1.0, x1)), max(0.0, min(1.0, x2))))
    y1, y2 = sorted((max(0.0, min(1.0, y1)), max(0.0, min(1.0, y2))))
    if x2 <= x1 or y2 <= y1:
        return 0.0

    n = max(3, int(samples))
    inside = 0
    total = n * n
    # Centres de cellules plutôt que bords : une boîte qui touche seulement le
    # contour d'une zone ne devient pas artificiellement « à moitié dedans ».
    for iy in range(n):
        y = y1 + (iy + 0.5) * (y2 - y1) / n
        for ix in range(n):
            x = x1 + (ix + 0.5) * (x2 - x1) / n
            if point_in_polygon(x, y, poly):
                inside += 1
    return inside / total


def segment_side(ax: float, ay: float, bx: float, by: float,
                 px: float, py: float) -> float:
    """Signe du produit vectoriel AB × AP : > 0 d'un côté du segment, < 0 de
    l'autre, 0 sur la droite (AB). Sert à détecter le franchissement d'une ligne
    (changement de signe entre deux frames)."""
    return (bx - ax) * (py - ay) - (by - ay) * (px - ax)

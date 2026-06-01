# app/utils/plate_utils.py
"""
Utilitaires de normalisation et de comparaison floue (fuzzy) des plaques.

Pourquoi du fuzzy matching ?
  L'OCR confond régulièrement des caractères visuellement proches
  (O↔0, I↔1, S↔5, B↔8, Z↔2, G↔6…). Une simple égalité SQL raterait
  donc des plaques pourtant correctes. On compare via une distance de
  Levenshtein normalisée, calculée à la fois sur la chaîne brute et sur
  une chaîne « repliée » (OCR-folded) où les confusions classiques sont
  ramenées à une classe canonique.

Dépendance optionnelle : `rapidfuzz` (rapide, sans compilation C).
  Si absent, on bascule sur une implémentation pure-Python de Levenshtein
  → la route /plates/search fonctionne dans tous les cas.
"""
from __future__ import annotations

import re

# rapidfuzz est optionnel — fallback pur-Python si indisponible.
try:
    from rapidfuzz.distance import Levenshtein as _RFLevenshtein  # type: ignore
    _HAS_RAPIDFUZZ = True
except Exception:  # pragma: no cover - dépend de l'environnement
    _RFLevenshtein = None
    _HAS_RAPIDFUZZ = False


# Confusions OCR classiques → classe canonique.
# Conservateur volontairement (paires visuellement très proches uniquement)
# pour limiter les faux positifs lors du repliement.
_OCR_FOLD = {
    "O": "0", "Q": "0", "0": "0",
    "I": "1", "1": "1",
    "S": "5", "5": "5",
    "B": "8", "8": "8",
    "Z": "2", "2": "2",
    "G": "6", "6": "6",
}

_NON_ALNUM = re.compile(r"[^A-Z0-9]")


def normalize_plate(raw: str | None) -> str:
    """
    Normalise une plaque : majuscules + suppression de tout caractère non
    alphanumérique (espaces, tirets, points…).

    Ex. "1-abc 234" → "1ABC234".
    """
    if not raw:
        return ""
    return _NON_ALNUM.sub("", raw.upper())


def ocr_fold(plate: str) -> str:
    """Replie les caractères OCR-confusables vers leur classe canonique."""
    return "".join(_OCR_FOLD.get(c, c) for c in plate)


def _levenshtein_distance(a: str, b: str) -> int:
    """Distance de Levenshtein (pure Python — fallback sans rapidfuzz)."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)

    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        current = [i]
        for j, cb in enumerate(b, start=1):
            cost = 0 if ca == cb else 1
            current.append(min(
                previous[j] + 1,        # suppression
                current[j - 1] + 1,     # insertion
                previous[j - 1] + cost  # substitution
            ))
        previous = current
    return previous[-1]


def _normalized_similarity(a: str, b: str) -> float:
    """Similarité de Levenshtein normalisée ∈ [0.0, 1.0] (1.0 = identique)."""
    if not a and not b:
        return 1.0
    if _HAS_RAPIDFUZZ:
        return float(_RFLevenshtein.normalized_similarity(a, b))
    max_len = max(len(a), len(b))
    if max_len == 0:
        return 1.0
    return 1.0 - (_levenshtein_distance(a, b) / max_len)


def plate_similarity(a: str, b: str) -> float:
    """
    Score de similarité ∈ [0.0, 1.0] entre deux plaques normalisées.

    Prend le maximum entre :
      - la similarité directe (chaînes normalisées)
      - la similarité sur les chaînes OCR-repliées (tolère O↔0, I↔1…)
    """
    direct = _normalized_similarity(a, b)
    folded = _normalized_similarity(ocr_fold(a), ocr_fold(b))
    return max(direct, folded)

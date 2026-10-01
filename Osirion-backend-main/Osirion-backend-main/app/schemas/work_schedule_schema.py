# app/schemas/work_schedule_schema.py
"""
Schémas des régimes horaires (jours, créneaux, fuseau, tolérance d'absence).

La validation est volontairement stricte : ces données sont consommées par le
Core en production, et un créneau malformé y produirait soit une exception dans
la boucle caméra, soit une surveillance silencieusement inactive.
"""
from pydantic import BaseModel, Field, field_validator
from typing import Optional, Dict, List
from datetime import datetime
from zoneinfo import ZoneInfo

JOURS_VALIDES = {"0", "1", "2", "3", "4", "5", "6"}   # 0 = lundi (datetime.weekday())

# Bornes de la tolérance d'absence : sous 30 s on signalerait le moindre
# déplacement, au-delà de 8 h le régime ne surveille plus rien.
TOLERANCE_MIN_S, TOLERANCE_MAX_S = 30, 8 * 3600

# Fuseaux du parc, pour les messages d'erreur. Piège : « Africa/Cotonou »
# N'EXISTE PAS dans la base IANA — le Bénin, c'est « Africa/Porto-Novo ».
FUSEAUX_SUGGERES = (
    "Africa/Niamey", "Africa/Accra", "Africa/Lome", "Africa/Bamako", "Africa/Porto-Novo",
)


def default_work_segments() -> Dict[str, List[List[str]]]:
    """Modèle réseau : activité H24, sauf pause prière le vendredi 13 h–14 h.

    ``00:00→00:00`` désigne volontairement une journée complète. Le second
    créneau du vendredi se termine à minuit sans déborder sur le samedi.
    """
    return {
        "0": [["00:00", "00:00"]],
        "1": [["00:00", "00:00"]],
        "2": [["00:00", "00:00"]],
        "3": [["00:00", "00:00"]],
        "4": [["00:00", "13:00"], ["14:00", "00:00"]],
        "5": [["00:00", "00:00"]],
        "6": [["00:00", "00:00"]],
    }


def _minutes(hhmm: str) -> int:
    """"HH:MM" → minutes depuis minuit. Lève ValueError si la forme est invalide."""
    parts = str(hhmm).split(":")
    if len(parts) != 2:
        raise ValueError(f"Heure invalide : « {hhmm} » (forme attendue HH:MM).")
    try:
        h, m = int(parts[0]), int(parts[1])
    except ValueError:
        raise ValueError(f"Heure invalide : « {hhmm} » (forme attendue HH:MM).")
    if not (0 <= h <= 23 and 0 <= m <= 59):
        raise ValueError(f"Heure hors bornes : « {hhmm} ».")
    return h * 60 + m


def valider_segments(v):
    """Vérifie la forme {"0": [["08:00","12:00"], …], …}, l'absence de chevauchement,
    y compris entre deux jours pour les plages de nuit, et renvoie les créneaux
    TRIÉS (le Core reçoit toujours des données rangées)."""
    if not isinstance(v, dict):
        raise ValueError("Les créneaux doivent être un objet { jour: [[début, fin], …] }.")
    inconnus = {str(k) for k in v} - JOURS_VALIDES
    if inconnus:
        raise ValueError(
            f"Jours inconnus : {sorted(inconnus)}. Attendu « 0 » (lundi) à « 6 » (dimanche)."
        )
    propre: Dict[str, List[List[str]]] = {}
    semaine = []
    for jour, creneaux in v.items():
        jour = str(jour)
        if creneaux is None:
            creneaux = []
        if not isinstance(creneaux, list):
            raise ValueError(f"Jour « {jour} » : une liste de créneaux est attendue.")
        bornes = []
        for c in creneaux:
            if not isinstance(c, (list, tuple)) or len(c) != 2:
                raise ValueError(f"Jour « {jour} » : chaque créneau doit être [début, fin].")
            debut, fin = _minutes(c[0]), _minutes(c[1])
            # 00:00→00:00 est notre notation explicite pour une journée H24.
            # Toute autre égalité resterait ambiguë. Fin < début décrit une
            # plage de nuit : 22:00→06:00.
            if fin == debut:
                if debut != 0:
                    raise ValueError(
                        f"Jour « {jour} » : seul 00:00–00:00 peut avoir des "
                        "bornes identiques (journée complète)."
                    )
                fin_eval = 24 * 60
            else:
                fin_eval = fin if fin > debut else fin + 24 * 60
            bornes.append((debut, fin_eval, [str(c[0]), str(c[1])]))
            debut_semaine = int(jour) * 24 * 60 + debut
            semaine.append((
                debut_semaine,
                int(jour) * 24 * 60 + fin_eval,
                f"jour {jour} · {c[0]}–{c[1]}",
            ))
        bornes.sort()
        for (_d1, f1, c1), (d2, _f2, c2) in zip(bornes, bornes[1:]):
            if d2 < f1:
                raise ValueError(
                    f"Jour « {jour} » : les créneaux {c1[0]}–{c1[1]} et "
                    f"{c2[0]}–{c2[1]} se chevauchent."
                )
        propre[jour] = [c for _d, _f, c in bornes]

    # Détecte aussi un chevauchement ENTRE jours : lundi 22:00→06:00 ne peut pas
    # coexister avec mardi 05:00→08:00. Le décalage ±1 semaine couvre le passage
    # cyclique dimanche→lundi.
    WEEK = 7 * 24 * 60
    for i, (d1, f1, label1) in enumerate(semaine):
        for d2, f2, label2 in semaine[i + 1:]:
            overlap = any(
                max(d1, d2 + shift) < min(f1, f2 + shift)
                for shift in (-WEEK, 0, WEEK)
            )
            if overlap:
                raise ValueError(
                    f"Les créneaux « {label1} » et « {label2} » se chevauchent."
                )
    return propre


def valider_fuseau(v):
    """Refuse un fuseau IANA inconnu (échouer ici plutôt qu'en silence dans le Core)."""
    if v is None:
        raise ValueError("Le fuseau horaire ne peut pas être vide.")
    v = str(v).strip()
    try:
        ZoneInfo(v)
    except Exception:
        raise ValueError(
            f"Fuseau horaire inconnu : « {v} ». Utiliser un identifiant IANA, "
            f"par exemple : {', '.join(FUSEAUX_SUGGERES)}."
        )
    return v


def valider_tolerance(v):
    if v is None:
        raise ValueError("La tolérance d'absence ne peut pas être vide.")
    v = int(v)
    if not TOLERANCE_MIN_S <= v <= TOLERANCE_MAX_S:
        raise ValueError(
            f"La tolérance d'absence doit être comprise entre {TOLERANCE_MIN_S} s "
            f"et {TOLERANCE_MAX_S // 3600} h."
        )
    return v


def valider_nom(v):
    if v is None:
        raise ValueError("Le nom du régime ne peut pas être vide.")
    v = str(v).strip()
    if not v:
        raise ValueError("Le nom du régime est requis.")
    if len(v) > 100:
        raise ValueError("Le nom du régime est limité à 100 caractères.")
    return v


class WorkScheduleCreate(BaseModel):
    name: str = Field(max_length=100)
    description: Optional[str] = Field(default=None, max_length=255)
    timezone: str = Field(default="Africa/Niamey", max_length=64)
    segments: Dict[str, List[List[str]]] = Field(default_factory=default_work_segments)
    absence_tolerance_s: int = 600

    @field_validator("name")
    @classmethod
    def _check_name(cls, v):
        return valider_nom(v)

    @field_validator("segments")
    @classmethod
    def _check_segments(cls, v):
        return valider_segments(v)

    @field_validator("timezone")
    @classmethod
    def _check_timezone(cls, v):
        return valider_fuseau(v)

    @field_validator("absence_tolerance_s")
    @classmethod
    def _check_tolerance(cls, v):
        return valider_tolerance(v)


class WorkScheduleUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=100)
    description: Optional[str] = Field(default=None, max_length=255)
    timezone: Optional[str] = Field(default=None, max_length=64)
    segments: Optional[Dict[str, List[List[str]]]] = None
    absence_tolerance_s: Optional[int] = None
    is_active: Optional[bool] = None

    @field_validator("name")
    @classmethod
    def _check_name(cls, v):
        return valider_nom(v)

    @field_validator("segments")
    @classmethod
    def _check_segments(cls, v):
        if v is None:
            raise ValueError("Les créneaux ne peuvent pas être vides.")
        return valider_segments(v)

    @field_validator("timezone")
    @classmethod
    def _check_timezone(cls, v):
        return valider_fuseau(v)

    @field_validator("absence_tolerance_s")
    @classmethod
    def _check_tolerance(cls, v):
        return valider_tolerance(v)

    @field_validator("is_active")
    @classmethod
    def _check_active(cls, v):
        if v is None:
            raise ValueError("Le statut actif ne peut pas être vide.")
        return v


class WorkScheduleRead(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    timezone: str
    segments: Dict[str, List[List[str]]]
    absence_tolerance_s: int
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None
    # Nombre de zones qui l'utilisent : l'UI doit pouvoir prévenir avant de
    # modifier un régime appliqué à 40 postes, ou d'en supprimer un.
    zones_count: int = 0

# app/models/work_schedule.py
"""
Régime horaire — jours, créneaux de travail et fuseau d'un groupe d'agences.

Sert la surveillance de PRÉSENCE AUX POSTES : une zone de type `presence` pointe
vers un régime, et toute modification du régime s'applique aussitôt à TOUTES les
zones qui le référencent (un réglage, N caméras).

Modèle par CRÉNEAUX plutôt que « début/fin + liste de pauses » : un jour est une
liste de créneaux travaillés, et les pauses sont simplement les trous entre eux.

    lundi  : [["00:00","00:00"]]                       ← journée complète H24
    vendredi : [["00:00","13:00"], ["14:00","00:00"]] ← pause prière 13 h–14 h

Ce format gère nativement les demi-journées et les horaires coupés, et réduit
l'évaluation à une seule question : « l'instant courant tombe-t-il dans un
créneau ? ».

⚠️ FUSEAU OBLIGATOIRE : le parc est à cheval sur deux fuseaux (Ghana, Togo et
Mali en UTC+0 ; Niger et Bénin en UTC+1). Un décalage global unique décalerait
d'une heure les horaires de la moitié des agences — absences fantômes à
l'ouverture, trous non détectés à la fermeture. Le fuseau appartient donc au
régime, pas à la configuration globale.
"""
from sqlmodel import SQLModel, Field
from sqlalchemy import Column, JSON
from typing import Optional, Dict, List
from datetime import datetime

# Clés de `segments` : "0" = lundi … "6" = dimanche. Même convention que
# datetime.weekday() et que Rule.schedule["days"], pour éviter deux conventions
# de numérotation des jours dans la même base de code.
JOURS = ("0", "1", "2", "3", "4", "5", "6")

# Tolérance par défaut avant qu'un poste vide soit signalable (secondes).
# 10 min : marge volontairement confortable — un agent assis derrière un
# comptoir est un cas de détection difficile, et une fausse absence n'est pas
# une file mal comptée mais une accusation implicite envers quelqu'un.
DEFAUT_TOLERANCE_ABSENCE_S = 600


class WorkSchedule(SQLModel, table=True):
    __tablename__ = "work_schedule"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(..., max_length=100, unique=True, index=True)
    description: Optional[str] = Field(default=None, max_length=255)

    # Identifiant IANA (ex. "Africa/Niamey", "Africa/Accra"). Attention :
    # "Africa/Cotonou" N'EXISTE PAS — le Bénin, c'est "Africa/Porto-Novo".
    timezone: str = Field(default="Africa/Niamey", max_length=64)

    # {"0": [["00:00","00:00"]], …} — heures LOCALES au fuseau.
    # 00:00→00:00 signifie une journée complète de 24 heures.
    segments: Dict[str, List[List[str]]] = Field(sa_column=Column(JSON, nullable=False))

    # Durée (s) pendant laquelle un poste doit rester inoccupé, DANS un créneau
    # travaillé, avant d'être signalé.
    absence_tolerance_s: int = Field(default=DEFAUT_TOLERANCE_ABSENCE_S)

    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = Field(default=None)

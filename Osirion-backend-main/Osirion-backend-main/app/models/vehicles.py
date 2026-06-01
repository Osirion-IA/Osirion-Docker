# app/models/vehicles.py
"""
Modèle Vehicle — registre des plaques d'immatriculation connues / surveillées.

C'est l'équivalent « véhicule » de la table People (côté reconnaissance faciale) :
  - People  → personnes connues identifiées par embedding facial
  - Vehicle → véhicules connus identifiés par texte de plaque (normalisé)

Le champ `plate_text` est stocké sous forme NORMALISÉE (majuscules, sans espaces
ni tirets) afin de fiabiliser la comparaison exacte et le fuzzy matching côté API.
"""
from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import datetime


class Vehicle(SQLModel, table=True):
    __tablename__ = "vehicle"

    id: Optional[int] = Field(default=None, primary_key=True)

    # Texte de plaque NORMALISÉ (uppercase, alphanumérique uniquement) — unique.
    # Ex. saisie "1-ABC 234" → stockée "1ABC234".
    plate_text: str = Field(..., max_length=20, unique=True, index=True)

    # Propriétaire déclaré (facultatif).
    owner_name: Optional[str] = Field(default=None, max_length=100)

    # Véhicule sur liste de surveillance / blacklist (déclenche une alerte).
    is_blacklisted: bool = Field(default=False, index=True)

    # Métadonnées facultatives utiles à l'exploitation.
    notes: Optional[str] = Field(default=None, max_length=255)

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = Field(default=None)

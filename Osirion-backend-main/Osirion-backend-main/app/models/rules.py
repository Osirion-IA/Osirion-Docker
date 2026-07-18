# app/models/rules.py
"""
Règle du moteur de décision : « SI un événement <trigger> satisfait <conditions>
PENDANT <schedule> ALORS créer une alerte <kind> (+ notifier <notify_channels>) ».

Évaluée côté BACKEND à l'ingestion d'événement (cf. services/rule_engine.py) —
le Core reste « bête » (il ne fait qu'émettre des événements).

Champs JSON (libres, sans couplage) :
- conditions : {"min_count": 5} | {"min_wait_s": 300} | {"direction": "in"} …
- schedule   : {"days": [0..6] (0=lundi), "from": "HH:MM", "to": "HH:MM"} — gère le
               passage minuit (from > to). None = toujours armé.
- notify_channels : ["email", "webhook"] — [] / None = alerte seule (pas de notif auto).
"""
from sqlmodel import SQLModel, Field
from sqlalchemy import Column, JSON
from typing import Optional, List, Dict, Any
from datetime import datetime


class Rule(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(..., max_length=100)
    # Type d'événement déclencheur (émis par l'Event Engine).
    trigger: str = Field(..., max_length=30)
    # Restriction optionnelle à une zone (match event.meta.zone_id). None = toutes.
    zone_id: Optional[int] = Field(default=None)
    conditions: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    schedule: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    # Type d'alerte émise : "intrusion" | "crowd" | "queue" | "custom".
    kind: str = Field(default="custom", max_length=20)
    notify_channels: Optional[List[str]] = Field(default=None, sa_column=Column(JSON))
    is_active: bool = Field(default=True)
    organization_id: Optional[int] = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = Field(default=None)

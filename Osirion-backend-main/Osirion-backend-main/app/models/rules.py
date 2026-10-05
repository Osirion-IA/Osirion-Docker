# app/models/rules.py
"""
Règle du moteur de décision : « SI un événement <trigger> satisfait <conditions>
PENDANT <schedule> ALORS créer une alerte <kind> (+ notifier <notify_channels>) ».

Évaluée côté BACKEND à l'ingestion d'événement (cf. services/rule_engine.py) —
le Core reste « bête » (il ne fait qu'émettre des événements).

Champs JSON (libres, sans couplage) :
- conditions : deux formats acceptés par le moteur (cf. services/rule_engine.py) —
    • hérité (rétro-compatible) : {"min_count": 5} | {"min_wait_s": 300} | {"direction": "in"}
    • prédicats typés          : {"all": [{"field": "count", "op": ">=", "value": 5},
                                          {"field": "count", "op": "<=", "value": 20}]}
                                 ("all" = ET, "any" = OU ; op ∈ >= > <= < == != between in)
- schedule   : {"days": [0..6] (0=lundi), "from": "HH:MM", "to": "HH:MM"} — gère le
               passage minuit (from > to). None = toujours armé.
- notify_channels : ["email", "webhook"] — [] / None = alerte seule (pas de notif auto).

Sévérité & anti-spam :
- severity   : "info" | "warning" | "critical" (routage notifications & couleur UI).
- cooldown_s : délai mini (secondes) entre deux déclenchements de CETTE règle sur une
               MÊME zone — évite la rafale d'alertes tant qu'un événement persiste.
- last_triggered_at / trigger_count : observabilité (dernier tir, nb de tirs).
"""
from sqlmodel import SQLModel, Field
from sqlalchemy import Column, Integer, ForeignKey, JSON
from typing import Optional, List, Dict, Any
from datetime import datetime

# Niveaux de sévérité (ordre croissant de gravité).
SEVERITIES = ("info", "warning", "critical")


class Rule(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(..., max_length=100)
    # Type d'événement déclencheur (émis par l'Event Engine).
    trigger: str = Field(..., max_length=30)
    # Restriction optionnelle à une zone (match event.meta.zone_id). None = toutes.
    zone_id: Optional[int] = Field(default=None)
    # Portée groupe/régime : les événements de présence portent schedule_id.
    # Une seule règle couvre ainsi toutes les zones et caméras rattachées au même
    # groupe. CASCADE évite qu'une règle devienne accidentellement globale après
    # suppression forcée du régime.
    work_schedule_id: Optional[int] = Field(
        default=None,
        sa_column=Column(
            Integer,
            ForeignKey("work_schedule.id", ondelete="CASCADE"),
            nullable=True,
            index=True,
        ),
    )
    conditions: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    schedule: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    # Type d'alerte émise : "intrusion" | "crowd" | "queue" | "custom".
    kind: str = Field(default="custom", max_length=20)
    # Sévérité métier : "info" | "warning" | "critical".
    severity: str = Field(default="warning", max_length=20)
    notify_channels: Optional[List[str]] = Field(default=None, sa_column=Column(JSON))
    # Anti-spam : délai mini (s) entre deux tirs de la règle sur une même zone.
    #
    # Le défaut était 0 — AUCUNE temporisation : toute règle créée depuis
    # l'interface naissait en mesure d'alerter à chaque événement. Pour un
    # déclencheur répétitif, le regroupement par épisode du moteur protège
    # (cf. rule_engine._STATE_TRIGGERS) ; pour les autres, rien ne bornait le
    # débit. 300 s est un plancher raisonnable, ajustable par règle dans l'UI.
    # Mettre 0 reste possible et désactive explicitement la temporisation.
    cooldown_s: int = Field(default=300)
    is_active: bool = Field(default=True)
    # Observabilité.
    last_triggered_at: Optional[datetime] = Field(default=None)
    trigger_count: int = Field(default=0)
    organization_id: Optional[int] = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = Field(default=None)

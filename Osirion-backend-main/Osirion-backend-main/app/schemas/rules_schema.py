# app/schemas/rules_schema.py
from pydantic import BaseModel, field_validator
from typing import Optional, List, Dict, Any
from datetime import datetime

from app.models.rules import SEVERITIES


class RuleCreate(BaseModel):
    name: str
    trigger: str
    zone_id: Optional[int] = None
    conditions: Optional[Dict[str, Any]] = None
    schedule: Optional[Dict[str, Any]] = None
    kind: str = "custom"
    severity: str = "warning"
    cooldown_s: int = 0
    notify_channels: Optional[List[str]] = None

    @field_validator("severity")
    @classmethod
    def _check_severity(cls, v):
        if v is not None and v not in SEVERITIES:
            raise ValueError(f"severity doit être l'un de {SEVERITIES}")
        return v


class RuleUpdate(BaseModel):
    name: Optional[str] = None
    trigger: Optional[str] = None
    zone_id: Optional[int] = None
    conditions: Optional[Dict[str, Any]] = None
    schedule: Optional[Dict[str, Any]] = None
    kind: Optional[str] = None
    severity: Optional[str] = None
    cooldown_s: Optional[int] = None
    notify_channels: Optional[List[str]] = None
    is_active: Optional[bool] = None

    @field_validator("severity")
    @classmethod
    def _check_severity(cls, v):
        if v is not None and v not in SEVERITIES:
            raise ValueError(f"severity doit être l'un de {SEVERITIES}")
        return v


class RuleRead(BaseModel):
    id: int
    name: str
    trigger: str
    zone_id: Optional[int] = None
    conditions: Optional[Dict[str, Any]] = None
    schedule: Optional[Dict[str, Any]] = None
    kind: str
    severity: str = "warning"
    cooldown_s: int = 0
    notify_channels: Optional[List[str]] = None
    is_active: bool
    last_triggered_at: Optional[datetime] = None
    trigger_count: int = 0
    created_at: datetime

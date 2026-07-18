# app/schemas/rules_schema.py
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime


class RuleCreate(BaseModel):
    name: str
    trigger: str
    zone_id: Optional[int] = None
    conditions: Optional[Dict[str, Any]] = None
    schedule: Optional[Dict[str, Any]] = None
    kind: str = "custom"
    notify_channels: Optional[List[str]] = None


class RuleUpdate(BaseModel):
    name: Optional[str] = None
    trigger: Optional[str] = None
    zone_id: Optional[int] = None
    conditions: Optional[Dict[str, Any]] = None
    schedule: Optional[Dict[str, Any]] = None
    kind: Optional[str] = None
    notify_channels: Optional[List[str]] = None
    is_active: Optional[bool] = None


class RuleRead(BaseModel):
    id: int
    name: str
    trigger: str
    zone_id: Optional[int] = None
    conditions: Optional[Dict[str, Any]] = None
    schedule: Optional[Dict[str, Any]] = None
    kind: str
    notify_channels: Optional[List[str]] = None
    is_active: bool
    created_at: datetime

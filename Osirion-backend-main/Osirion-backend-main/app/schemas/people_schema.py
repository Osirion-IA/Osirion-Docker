# app/schemas/people_schemas.py
from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime

class PeopleCreate(BaseModel):
    first_name: str
    last_name: str
    phone: str
    email: EmailStr
    addresse: str
    image_url: str
    embeddings: Optional[list[float]] = None

class PeopleRead(BaseModel):
    id: int
    first_name: str
    last_name: str
    phone: str
    email: EmailStr
    addresse: str
    image_url: str
    is_blacklisted: bool = False
    blacklist_reason: Optional[str] = None
    created_at: datetime


class PersonBlacklistUpdate(BaseModel):
    blacklisted: bool = True
    reason: Optional[str] = None

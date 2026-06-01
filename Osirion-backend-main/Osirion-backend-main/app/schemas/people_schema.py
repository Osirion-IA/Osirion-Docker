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
    created_at: datetime

from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import Optional
from app.models.users import UserRole

class UserCreate(BaseModel):
    fullName: str
    email: EmailStr
    usr_password: str
    role: UserRole = UserRole.VIEWER

class UserRead(BaseModel):
    id: int
    fullName: str
    email: EmailStr
    role: str
    is_active: bool
    is_verified: bool
    created_at: datetime
    last_login: Optional[datetime]

    class Config:
        from_attributes = True
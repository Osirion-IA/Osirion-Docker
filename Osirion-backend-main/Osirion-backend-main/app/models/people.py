# app/models/people.py
from sqlmodel import SQLModel, Field
from sqlalchemy import Column
from typing import Optional
from datetime import datetime
from pgvector.sqlalchemy import Vector

class People(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    first_name: str = Field(..., max_length=50)
    last_name: str = Field(..., max_length=50)
    phone: str = Field(..., max_length=20, unique=True)
    email: str = Field(..., max_length=100, unique=True)
    addresse: str = Field(..., max_length=100)
    image_url: str
    embeddings: list[float] = Field(sa_column=Column(Vector(512)))

    # ── Liste de surveillance / blacklist ─────────────────────────────────────
    # Personne surveillée : sa reconnaissance déclenche une alerte (overlay rouge
    # + toast/son frontend). Défaut False → aucune régression sur l'existant.
    is_blacklisted: bool = Field(default=False, index=True)
    # Motif facultatif affiché dans l'alerte (ex. « recherché », « interdit de site »).
    blacklist_reason: Optional[str] = Field(default=None, max_length=255)

    created_at: datetime = Field(default_factory=datetime.utcnow)

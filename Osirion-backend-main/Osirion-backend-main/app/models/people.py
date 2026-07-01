# app/models/people.py
from sqlmodel import SQLModel, Field, Relationship
from sqlalchemy import Column, Integer, ForeignKey
from typing import Optional, List
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

    # ── Galerie multi-vecteurs (relation 1→N) ─────────────────────────────────
    # L'ancienne colonne unique `embeddings: Vector(512)` est SUPPRIMÉE : un seul
    # vecteur (centroïde moyenné) par personne plafonnait la similarité cosinus en
    # live (mélange d'angles/éclairages → point « flou » qui ne ressemble à aucune
    # pose réelle). Désormais chaque photo (et ses augmentations) produit UN vecteur
    # stocké dans `person_embeddings`, et la recherche fait du max-cosine par
    # personne (cf. Faiss_search_service). CASCADE → supprimer une personne purge
    # automatiquement tous ses embeddings.
    embeddings: List["PersonEmbedding"] = Relationship(
        back_populates="person",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )

    # ── Liste de surveillance / blacklist ─────────────────────────────────────
    # Personne surveillée : sa reconnaissance déclenche une alerte (overlay rouge
    # + toast/son frontend). Défaut False → aucune régression sur l'existant.
    is_blacklisted: bool = Field(default=False, index=True)
    # Motif facultatif affiché dans l'alerte (ex. « recherché », « interdit de site »).
    blacklist_reason: Optional[str] = Field(default=None, max_length=255)

    created_at: datetime = Field(default_factory=datetime.utcnow)


class PersonEmbedding(SQLModel, table=True):
    """Un vecteur facial 512-D appartenant à une personne (relation N→1).

    Plusieurs lignes par `person_id` (différents angles / éclairages / photos).
    La suppression de la personne parente supprime ses embeddings (ON DELETE
    CASCADE, géré à la fois côté ORM via `cascade` et côté DB via la FK)."""
    __tablename__ = "person_embeddings"

    id: Optional[int] = Field(default=None, primary_key=True)
    person_id: int = Field(
        sa_column=Column(
            Integer,
            ForeignKey("people.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
    embedding: List[float] = Field(sa_column=Column(Vector(512), nullable=False))

    person: Optional[People] = Relationship(back_populates="embeddings")

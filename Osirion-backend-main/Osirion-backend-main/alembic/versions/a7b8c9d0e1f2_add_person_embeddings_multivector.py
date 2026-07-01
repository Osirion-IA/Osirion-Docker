"""add person_embeddings (galerie multi-vecteurs) + migration de people.embeddings

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-06-26 12:00:00.000000

Refonte multi-vecteurs : passage d'UN vecteur (centroïde) par personne à PLUSIEURS
vecteurs par personne (différents angles/éclairages), pour casser le plafond de
similarité cosinus en live.

Étapes (idempotentes vis-à-vis des données) :
  1. crée la table `person_embeddings` (FK people.id ON DELETE CASCADE) ;
  2. recopie les embeddings existants (people.embeddings) → 1 ligne par personne ;
  3. supprime la colonne people.embeddings.

Le downgrade restaure la colonne et y remet UN vecteur par personne (le premier).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector  # type vecteur pgvector

revision: str = 'a7b8c9d0e1f2'
down_revision: Union[str, Sequence[str], None] = 'f6a7b8c9d0e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1) Table enfant (relation 1→N)
    op.create_table(
        'person_embeddings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('person_id', sa.Integer(), nullable=False),
        sa.Column('embedding', Vector(512), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['person_id'], ['people.id'], ondelete='CASCADE'),
    )
    op.create_index(
        'ix_person_embeddings_person_id', 'person_embeddings', ['person_id'], unique=False
    )

    # 2) Backfill : 1 ligne par personne ayant déjà un embedding centroïde.
    op.execute(
        """
        INSERT INTO person_embeddings (person_id, embedding)
        SELECT id, embeddings FROM people WHERE embeddings IS NOT NULL
        """
    )

    # 3) Suppression de l'ancienne colonne mono-vecteur.
    op.drop_column('people', 'embeddings')


def downgrade() -> None:
    # Restaure la colonne mono-vecteur (nullable).
    op.add_column('people', sa.Column('embeddings', Vector(512), nullable=True))

    # Remet UN vecteur par personne (le plus petit id = le premier enrôlé).
    op.execute(
        """
        UPDATE people p
        SET embeddings = pe.embedding
        FROM (
            SELECT DISTINCT ON (person_id) person_id, embedding
            FROM person_embeddings
            ORDER BY person_id, id
        ) pe
        WHERE pe.person_id = p.id
        """
    )

    op.drop_index('ix_person_embeddings_person_id', table_name='person_embeddings')
    op.drop_table('person_embeddings')

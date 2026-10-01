"""remove facial module: drop people/person_embeddings + person_id + module toggles

Retrait complet de la reconnaissance faciale (InsightFace/pgvector/FAISS) et du
sous-système de bascule de modules par caméra/groupe, dans le cadre de la refonte
« intelligence opérationnelle anonyme ». Réversible (downgrade restaure le schéma).

Revision ID: a2b3c4d5e6f7
Revises: f1e2d3c4b5a6
Create Date: 2026-07-17 12:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a2b3c4d5e6f7'
down_revision: Union[str, Sequence[str], None] = 'f1e2d3c4b5a6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Retire le facial. Les tables/colonnes FK sont retirées dans l'ordre des
    dépendances (person_embeddings + colonnes person_id AVANT la table people)."""
    # ── Galerie multi-vecteurs (pgvector) — FK vers people ──────────────────
    op.drop_table('person_embeddings')

    # ── Colonnes person_id (FK vers people) sur event et alert ──────────────
    # DROP COLUMN retire aussi la contrainte FK dépendante (PostgreSQL).
    op.drop_column('event', 'person_id')
    op.drop_column('alert', 'person_id')

    # ── Table people ────────────────────────────────────────────────────────
    op.drop_table('people')

    # ── Sous-système de bascule des modules IA (par caméra / groupe) ────────
    op.drop_column('camera', 'is_facial_active')
    op.drop_column('camera', 'is_lpr_active')
    op.drop_column('cameragroup', 'is_facial_active')
    op.drop_column('cameragroup', 'is_lpr_active')


def downgrade() -> None:
    """Restaure le schéma facial + les drapeaux de module (réversibilité)."""
    from pgvector.sqlalchemy import Vector

    # ── Drapeaux de module ──────────────────────────────────────────────────
    op.add_column('cameragroup', sa.Column('is_lpr_active', sa.Boolean(), nullable=False, server_default=sa.text('TRUE')))
    op.add_column('cameragroup', sa.Column('is_facial_active', sa.Boolean(), nullable=False, server_default=sa.text('TRUE')))
    op.add_column('camera', sa.Column('is_lpr_active', sa.Boolean(), nullable=False, server_default=sa.text('TRUE')))
    op.add_column('camera', sa.Column('is_facial_active', sa.Boolean(), nullable=False, server_default=sa.text('TRUE')))

    # ── Table people ────────────────────────────────────────────────────────
    op.create_table(
        'people',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('first_name', sa.String(length=50), nullable=False),
        sa.Column('last_name', sa.String(length=50), nullable=False),
        sa.Column('phone', sa.String(length=20), nullable=False),
        sa.Column('email', sa.String(length=100), nullable=False),
        sa.Column('addresse', sa.String(length=100), nullable=False),
        sa.Column('image_url', sa.Text(), nullable=False),
        sa.Column('is_blacklisted', sa.Boolean(), nullable=False, server_default=sa.text('FALSE')),
        sa.Column('blacklist_reason', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_people_email', 'people', ['email'], unique=True)
    op.create_index('ix_people_phone', 'people', ['phone'], unique=True)
    op.create_index('ix_people_is_blacklisted', 'people', ['is_blacklisted'], unique=False)

    # ── Galerie multi-vecteurs (pgvector) ───────────────────────────────────
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        'person_embeddings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('person_id', sa.Integer(), nullable=False),
        sa.Column('embedding', Vector(512), nullable=False),
        sa.ForeignKeyConstraint(['person_id'], ['people.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_person_embeddings_person_id', 'person_embeddings', ['person_id'], unique=False)

    # ── Colonnes person_id sur event et alert ───────────────────────────────
    op.add_column('event', sa.Column('person_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_event_person_id', 'event', 'people', ['person_id'], ['id'])
    op.add_column('alert', sa.Column('person_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_alert_person_id', 'alert', 'people', ['person_id'], ['id'], ondelete='SET NULL')

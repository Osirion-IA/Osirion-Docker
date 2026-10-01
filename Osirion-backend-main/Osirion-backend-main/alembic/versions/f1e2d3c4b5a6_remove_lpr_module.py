"""remove LPR module: drop vehicle table + plate/vehicle columns on event and alert

Retrait complet du module LPR/ANPR (reconnaissance de plaques) dans le cadre de
la refonte « intelligence opérationnelle ». Réversible : le downgrade restaure la
table vehicle et les colonnes associées (cf. migration c3d4e5f6a7b8 d'origine).

Revision ID: f1e2d3c4b5a6
Revises: b8c9d0e1f2a3
Create Date: 2026-07-17 00:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'f1e2d3c4b5a6'
down_revision: Union[str, Sequence[str], None] = 'b8c9d0e1f2a3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Retire les colonnes/tables LPR. Les colonnes FK sont retirées AVANT la
    table vehicle (dépendances)."""
    # ── alert.vehicle_id (FK → vehicle) ─────────────────────────────────────
    # Le DROP COLUMN retire aussi la contrainte FK dépendante (PostgreSQL).
    op.drop_column('alert', 'vehicle_id')

    # ── event : FK nommée puis colonnes plaque ──────────────────────────────
    op.drop_constraint('fk_event_vehicle_id', 'event', type_='foreignkey')
    op.drop_column('event', 'vehicle_id')
    op.drop_column('event', 'plate_text_detected')

    # ── table vehicle (+ index) ─────────────────────────────────────────────
    op.drop_index('ix_vehicle_is_blacklisted', table_name='vehicle')
    op.drop_index('ix_vehicle_plate_text', table_name='vehicle')
    op.drop_table('vehicle')


def downgrade() -> None:
    """Restaure la table vehicle et les colonnes plaque/vehicle (réversibilité)."""
    op.create_table(
        'vehicle',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('plate_text', sa.String(length=20), nullable=False),
        sa.Column('owner_name', sa.String(length=100), nullable=True),
        sa.Column('is_blacklisted', sa.Boolean(), nullable=False, server_default=sa.text('FALSE')),
        sa.Column('notes', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_vehicle_plate_text', 'vehicle', ['plate_text'], unique=True)
    op.create_index('ix_vehicle_is_blacklisted', 'vehicle', ['is_blacklisted'], unique=False)

    op.add_column('event', sa.Column('plate_text_detected', sa.String(length=20), nullable=True))
    op.add_column('event', sa.Column('vehicle_id', sa.Integer(), nullable=True))
    op.create_foreign_key(
        'fk_event_vehicle_id', 'event', 'vehicle',
        ['vehicle_id'], ['id'], ondelete='SET NULL'
    )

    op.add_column('alert', sa.Column('vehicle_id', sa.Integer(), nullable=True))
    op.create_foreign_key(
        'fk_alert_vehicle_id', 'alert', 'vehicle',
        ['vehicle_id'], ['id'], ondelete='SET NULL'
    )

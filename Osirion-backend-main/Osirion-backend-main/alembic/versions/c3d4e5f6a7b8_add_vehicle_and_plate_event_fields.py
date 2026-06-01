"""add vehicle table and plate fields on event (LPR/ANPR module)

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-06-01 00:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, Sequence[str], None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema — table vehicle + colonnes plaque sur event."""
    # ── Table vehicle ───────────────────────────────────────────────────────
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

    # ── Colonnes LPR sur event ──────────────────────────────────────────────
    op.add_column('event', sa.Column('plate_text_detected', sa.String(length=20), nullable=True))
    op.add_column('event', sa.Column('vehicle_id', sa.Integer(), nullable=True))
    op.create_foreign_key(
        'fk_event_vehicle_id', 'event', 'vehicle',
        ['vehicle_id'], ['id'], ondelete='SET NULL'
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('fk_event_vehicle_id', 'event', type_='foreignkey')
    op.drop_column('event', 'vehicle_id')
    op.drop_column('event', 'plate_text_detected')
    op.drop_index('ix_vehicle_is_blacklisted', table_name='vehicle')
    op.drop_index('ix_vehicle_plate_text', table_name='vehicle')
    op.drop_table('vehicle')

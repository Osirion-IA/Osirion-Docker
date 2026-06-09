"""add alert table (centre d'alertes blacklist)

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-06-09 00:30:00.000000

Migration ADDITIVE : crée une nouvelle table `alert`. N'altère aucune table
existante → aucun risque pour les données en place.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, Sequence[str], None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema — table alert."""
    op.create_table(
        'alert',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('event_id', sa.Integer(), nullable=True),
        sa.Column('kind', sa.String(length=20), nullable=False),
        sa.Column('label', sa.String(length=255), nullable=False),
        sa.Column('reason', sa.String(length=255), nullable=True),
        sa.Column('camera_id', sa.Integer(), nullable=True),
        sa.Column('person_id', sa.Integer(), nullable=True),
        sa.Column('vehicle_id', sa.Integer(), nullable=True),
        sa.Column('snapshot_url', sa.String(length=255), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False, server_default=sa.text("'new'")),
        sa.Column('acknowledged_at', sa.DateTime(), nullable=True),
        sa.Column('acknowledged_by', sa.Integer(), nullable=True),
        sa.Column('notified_at', sa.DateTime(), nullable=True),
        sa.Column('notified_channel', sa.String(length=40), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['event_id'], ['event.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['person_id'], ['people.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['vehicle_id'], ['vehicle.id'], ondelete='SET NULL'),
    )
    op.create_index('ix_alert_status', 'alert', ['status'], unique=False)
    op.create_index('ix_alert_created_at', 'alert', ['created_at'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_alert_created_at', table_name='alert')
    op.drop_index('ix_alert_status', table_name='alert')
    op.drop_table('alert')

"""add rule table (Decision Engine — Phase E)

Additif : moteur de règles (trigger + conditions + plage horaire + actions).
Aucune table existante modifiée.

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-07-18 14:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'd5e6f7a8b9c0'
down_revision: Union[str, Sequence[str], None] = 'c4d5e6f7a8b9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'rule',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('trigger', sa.String(length=30), nullable=False),
        sa.Column('zone_id', sa.Integer(), nullable=True),
        sa.Column('conditions', sa.JSON(), nullable=True),
        sa.Column('schedule', sa.JSON(), nullable=True),
        sa.Column('kind', sa.String(length=20), nullable=False, server_default='custom'),
        sa.Column('notify_channels', sa.JSON(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('TRUE')),
        sa.Column('organization_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_rule_organization_id', 'rule', ['organization_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_rule_organization_id', table_name='rule')
    op.drop_table('rule')

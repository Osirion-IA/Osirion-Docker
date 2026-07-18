"""add zone and count_line tables (spatial primitives — Phase B)

Primitives spatiales par caméra (Vision Engine anonyme) : zones (polygones) et
lignes de comptage (segments), coordonnées normalisées [0,1]. Additif — aucune
table existante modifiée.

Revision ID: b3c4d5e6f7a8
Revises: a2b3c4d5e6f7
Create Date: 2026-07-18 00:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'b3c4d5e6f7a8'
down_revision: Union[str, Sequence[str], None] = 'a2b3c4d5e6f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'zone',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('camera_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('kind', sa.String(length=20), nullable=False, server_default='generic'),
        sa.Column('polygon', sa.JSON(), nullable=False),
        sa.Column('color', sa.String(length=20), nullable=True),
        sa.Column('organization_id', sa.Integer(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('TRUE')),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['camera_id'], ['camera.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_zone_camera_id', 'zone', ['camera_id'], unique=False)
    op.create_index('ix_zone_organization_id', 'zone', ['organization_id'], unique=False)

    op.create_table(
        'count_line',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('camera_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('point_a', sa.JSON(), nullable=False),
        sa.Column('point_b', sa.JSON(), nullable=False),
        sa.Column('in_direction', sa.String(length=10), nullable=False, server_default='positive'),
        sa.Column('organization_id', sa.Integer(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('TRUE')),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['camera_id'], ['camera.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_count_line_camera_id', 'count_line', ['camera_id'], unique=False)
    op.create_index('ix_count_line_organization_id', 'count_line', ['organization_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_count_line_organization_id', table_name='count_line')
    op.drop_index('ix_count_line_camera_id', table_name='count_line')
    op.drop_table('count_line')
    op.drop_index('ix_zone_organization_id', table_name='zone')
    op.drop_index('ix_zone_camera_id', table_name='zone')
    op.drop_table('zone')

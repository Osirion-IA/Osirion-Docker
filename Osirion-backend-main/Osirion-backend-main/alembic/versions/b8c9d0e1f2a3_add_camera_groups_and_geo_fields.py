"""add camera groups (VMS) + geo fields + local module flags

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-07-01 08:00:00.000000

Migration ADDITIVE :
  - ajoute à `camera` les drapeaux de module locaux (is_facial_active,
    is_lpr_active — défaut TRUE) et les champs géospatiaux (latitude, longitude,
    bearing) pour la cartographie ;
  - crée la table `cameragroup` (groupes VMS avec bascule de module en masse) ;
  - crée la table d'association N↔N `camera_group_link` (FK ON DELETE CASCADE).

Les valeurs par défaut (server_default) garantissent qu'aucune ligne caméra
existante ne devient NON conforme : chaque caméra reste pleinement active.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'b8c9d0e1f2a3'
down_revision: Union[str, Sequence[str], None] = 'a7b8c9d0e1f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # ── camera : drapeaux de module locaux + géo ──────────────────────────────
    op.add_column(
        'camera',
        sa.Column('is_facial_active', sa.Boolean(), nullable=False,
                  server_default=sa.text('true')),
    )
    op.add_column(
        'camera',
        sa.Column('is_lpr_active', sa.Boolean(), nullable=False,
                  server_default=sa.text('true')),
    )
    op.add_column('camera', sa.Column('latitude', sa.Float(), nullable=True))
    op.add_column('camera', sa.Column('longitude', sa.Float(), nullable=True))
    op.add_column(
        'camera',
        sa.Column('bearing', sa.Float(), nullable=True, server_default=sa.text('0.0')),
    )

    # ── cameragroup ───────────────────────────────────────────────────────────
    op.create_table(
        'cameragroup',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('description', sa.String(length=255), nullable=True),
        sa.Column('is_facial_active', sa.Boolean(), nullable=False,
                  server_default=sa.text('true')),
        sa.Column('is_lpr_active', sa.Boolean(), nullable=False,
                  server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_cameragroup_name', 'cameragroup', ['name'], unique=True)

    # ── camera_group_link (N↔N) ───────────────────────────────────────────────
    op.create_table(
        'camera_group_link',
        sa.Column('camera_id', sa.Integer(), nullable=False),
        sa.Column('group_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['camera_id'], ['camera.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['group_id'], ['cameragroup.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('camera_id', 'group_id'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('camera_group_link')
    op.drop_index('ix_cameragroup_name', table_name='cameragroup')
    op.drop_table('cameragroup')
    op.drop_column('camera', 'bearing')
    op.drop_column('camera', 'longitude')
    op.drop_column('camera', 'latitude')
    op.drop_column('camera', 'is_lpr_active')
    op.drop_column('camera', 'is_facial_active')

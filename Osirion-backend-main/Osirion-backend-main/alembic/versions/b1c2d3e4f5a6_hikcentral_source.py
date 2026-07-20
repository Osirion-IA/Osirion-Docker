"""source de flux HikCentral : catalogue caméras par groupe

Additif (aucune donnée perdue) :
- camera.source_type    : "rtsp" (défaut, caméra RTSP manuelle) | "hikcentral".
- camera.hik_index_code : cameraIndexCode HikCentral (clé de mapping), nullable.
- camera.hik_status     : état HikCentral (1=en ligne, 2=hors-ligne), nullable.
- camera.rtsp_url       : rendu NULLABLE — une caméra HikCentral n'a pas d'URL
                          statique (résolue à la volée via previewURLs / rtsp_s).
- cameragroup.hik_region_code : indexCode de l'Area HikCentral (mapping groupe).

Revision ID: b1c2d3e4f5a6
Revises: a1b2c3d4e5f6
Create Date: 2026-07-20 16:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'b1c2d3e4f5a6'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('camera', sa.Column('source_type', sa.String(length=20), nullable=False, server_default='rtsp'))
    op.add_column('camera', sa.Column('hik_index_code', sa.String(length=64), nullable=True))
    op.add_column('camera', sa.Column('hik_status', sa.Integer(), nullable=True))
    op.create_index('ix_camera_hik_index_code', 'camera', ['hik_index_code'], unique=False)
    op.alter_column('camera', 'rtsp_url', existing_type=sa.String(), nullable=True)
    op.add_column('cameragroup', sa.Column('hik_region_code', sa.String(length=64), nullable=True))
    op.create_index('ix_cameragroup_hik_region_code', 'cameragroup', ['hik_region_code'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_cameragroup_hik_region_code', table_name='cameragroup')
    op.drop_column('cameragroup', 'hik_region_code')
    op.alter_column('camera', 'rtsp_url', existing_type=sa.String(), nullable=False)
    op.drop_index('ix_camera_hik_index_code', table_name='camera')
    op.drop_column('camera', 'hik_status')
    op.drop_column('camera', 'hik_index_code')
    op.drop_column('camera', 'source_type')

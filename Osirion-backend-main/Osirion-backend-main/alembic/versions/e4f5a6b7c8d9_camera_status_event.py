"""table camera_status_event (historique de connectivité des caméras)

Persiste les transitions d'état (online/offline/connecting/stalled/stopped) pour
reconstituer un historique de disponibilité — la santé Core étant éphémère.

Revision ID: e4f5a6b7c8d9
Revises: d3e4f5a6b7c8
Create Date: 2026-07-30
"""
from alembic import op
import sqlalchemy as sa

revision = "e4f5a6b7c8d9"
down_revision = "d3e4f5a6b7c8"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "camera_status_event",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("camera_id", sa.Integer(), nullable=False, index=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("prev_status", sa.String(length=20), nullable=True),
        sa.Column("reconnection_attempts", sa.Integer(), nullable=True),
        sa.Column("reason", sa.String(length=255), nullable=True),
        sa.Column("timestamp", sa.DateTime(), nullable=False, index=True),
    )
    op.create_index("ix_camstatus_cam_ts", "camera_status_event", ["camera_id", "timestamp"])


def downgrade():
    op.drop_index("ix_camstatus_cam_ts", table_name="camera_status_event")
    op.drop_table("camera_status_event")

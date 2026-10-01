"""index analytics sur event (camera_id, event_type, timestamp)

L'analytique (footfall, occupancy, queues, insights, by-camera, incidents) filtre
systématiquement `event` par caméra + type + fenêtre temporelle. Sans index, chaque
chargement d'onglet = full scan → coûteux dès que le volume grossit. Index couvrant.

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
Create Date: 2026-07-21
"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "c2d3e4f5a6b7"
down_revision = "b1c2d3e4f5a6"
branch_labels = None
depends_on = None

INDEX_NAME = "ix_event_camera_type_ts"


def upgrade():
    # if_not_exists : idempotent si l'index a déjà été créé hors migration.
    op.create_index(
        INDEX_NAME, "event", ["camera_id", "event_type", "timestamp"],
        unique=False, if_not_exists=True,
    )


def downgrade():
    op.drop_index(INDEX_NAME, table_name="event", if_exists=True)

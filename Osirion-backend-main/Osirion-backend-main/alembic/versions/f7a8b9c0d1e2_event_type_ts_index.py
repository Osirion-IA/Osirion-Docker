"""index event (event_type, timestamp) pour l'analytique tout-parc

Les agrégats analytiques tout-parc (occupation, files, summary, insights) filtrent
`event` par (event_type, timestamp) SANS camera_id. L'index existant
ix_event_camera_type_ts commence par camera_id → inutilisable pour ces requêtes,
qui retombaient en full scan. Cet index (event_type, timestamp) les sert
directement, ORDER BY timestamp compris.

Revision ID: f7a8b9c0d1e2
Revises: e4f5a6b7c8d9
Create Date: 2026-07-31
"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "f7a8b9c0d1e2"
down_revision = "e4f5a6b7c8d9"
branch_labels = None
depends_on = None

INDEX_NAME = "ix_event_type_ts"


def upgrade():
    # if_not_exists : idempotent si l'index a déjà été créé hors migration.
    op.create_index(
        INDEX_NAME, "event", ["event_type", "timestamp"],
        unique=False, if_not_exists=True,
    )


def downgrade():
    op.drop_index(INDEX_NAME, table_name="event", if_exists=True)

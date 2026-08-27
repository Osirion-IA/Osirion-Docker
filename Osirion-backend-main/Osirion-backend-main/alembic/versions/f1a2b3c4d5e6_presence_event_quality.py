"""qualité des événements historiques de présence

Revision ID: f1a2b3c4d5e6
Revises: e0f1a2b3c4d5
Create Date: 2026-08-27
"""
from alembic import op


revision = "f1a2b3c4d5e6"
down_revision = "e0f1a2b3c4d5"
branch_labels = None
depends_on = None


def upgrade():
    # Conserve toutes les preuves, mais sépare explicitement l'historique produit
    # avant les garde-fous caméra/candidats de la série fiable actuelle.
    op.execute("""
        UPDATE event
        SET meta = (
            COALESCE(meta, '{}'::json)::jsonb
            || jsonb_build_object(
                'presence_data_quality', 'archived',
                'presence_schema_version', 1
            )
        )::json
        WHERE event_type IN ('POST_VACANT', 'POST_ABSENCE')
    """)
    op.execute("""
        UPDATE event
        SET meta = (
            meta::jsonb
            || jsonb_build_object(
                'presence_data_quality', 'reliable',
                'presence_schema_version', 2
            )
        )::json
        WHERE (
            event_type = 'POST_VACANT'
            AND meta::jsonb ? 'decision'
        ) OR (
            event_type = 'POST_ABSENCE'
            AND meta::jsonb ? 'resolution_reason'
        )
    """)


def downgrade():
    op.execute("""
        UPDATE event
        SET meta = (
            meta::jsonb - 'presence_data_quality' - 'presence_schema_version'
        )::json
        WHERE event_type IN ('POST_VACANT', 'POST_ABSENCE')
    """)

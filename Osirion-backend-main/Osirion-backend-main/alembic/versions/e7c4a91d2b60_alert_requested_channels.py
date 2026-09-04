"""conserve les canaux demandes pour la reprise des alertes

Revision ID: e7c4a91d2b60
Revises: 64b322f7fbe8
Create Date: 2026-09-04
"""
import sqlalchemy as sa
from alembic import op


revision = "e7c4a91d2b60"
down_revision = "64b322f7fbe8"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "alert",
        sa.Column("notify_requested_channels", sa.String(length=40), nullable=True),
    )
    # Les échecs anciens ne doivent pas être envoyés plusieurs jours plus tard.
    # On conserve leur diagnostic et on les marque explicitement comme épuisés.
    op.execute("""
        UPDATE alert AS a
        SET notify_requested_channels = CASE
                WHEN (r.notify_channels::jsonb ? 'email')
                 AND (r.notify_channels::jsonb ? 'webhook') THEN 'email,webhook'
                WHEN (r.notify_channels::jsonb ? 'email') THEN 'email'
                WHEN (r.notify_channels::jsonb ? 'webhook') THEN 'webhook'
                ELSE NULL
            END,
            notify_attempts = 5,
            notify_last_error = COALESCE(
                a.notify_last_error,
                'échec historique non rejoué: alerte devenue trop ancienne'
            )
        FROM rule AS r
        WHERE a.notified_at IS NULL
          AND a.notify_next_retry_at IS NULL
          AND a.notify_attempts = 0
          AND a.reason = r.name
          AND r.notify_channels IS NOT NULL
    """)


def downgrade():
    op.drop_column("alert", "notify_requested_channels")

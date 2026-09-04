"""reprise des notifications d'alerte échouées

Campagne d'observation d'août 2026 : 55 alertes sur 574 n'ont jamais été
délivrées, à cause de coupures DNS passagères sur le serveur de messagerie.
L'envoi n'était tenté qu'une fois : un hoquet réseau de quelques secondes
perdait l'alerte définitivement, sans que rien ne le signale.

Ces colonnes permettent de rejouer un envoi échoué et d'exposer l'échec.
Les alertes déjà en base sont laissées telles quelles : celles qui n'ont pas
de notified_at deviennent éligibles à une reprise dès le prochain cycle.

Revision ID: 64b322f7fbe8
Revises: f1a2b3c4d5e6
Create Date: 2026-09-04
"""
import sqlalchemy as sa
from alembic import op


revision = "64b322f7fbe8"
down_revision = "f1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "alert",
        sa.Column("notify_attempts", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "alert", sa.Column("notify_last_error", sa.String(length=255), nullable=True)
    )
    op.add_column(
        "alert", sa.Column("notify_next_retry_at", sa.DateTime(), nullable=True)
    )
    op.create_index(
        "ix_alert_notify_next_retry_at", "alert", ["notify_next_retry_at"]
    )


def downgrade():
    op.drop_index("ix_alert_notify_next_retry_at", table_name="alert")
    op.drop_column("alert", "notify_next_retry_at")
    op.drop_column("alert", "notify_last_error")
    op.drop_column("alert", "notify_attempts")

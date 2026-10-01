"""table notification_config (SMTP/webhook pilotés depuis l'UI)

Configuration des notifications (email SMTP + webhook) saisie depuis Paramètres →
Notifications. Singleton (id=1) ; mot de passe SMTP chiffré (Fernet). Prime sur le
.env quand renseigné, sinon repli .env.

Revision ID: a8b9c0d1e2f3
Revises: f7a8b9c0d1e2
Create Date: 2026-08-03
"""
from alembic import op
import sqlalchemy as sa

revision = "a8b9c0d1e2f3"
down_revision = "f7a8b9c0d1e2"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "notification_config",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("smtp_host", sa.String(length=255), nullable=True),
        sa.Column("smtp_port", sa.Integer(), nullable=True),
        sa.Column("smtp_user", sa.String(length=255), nullable=True),
        sa.Column("smtp_password_enc", sa.String(length=1024), nullable=True),
        sa.Column("smtp_from", sa.String(length=255), nullable=True),
        sa.Column("smtp_use_tls", sa.Boolean(), nullable=True),
        sa.Column("alert_email_to", sa.String(length=1024), nullable=True),
        sa.Column("alert_webhook_url", sa.String(length=1024), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
    )


def downgrade():
    op.drop_table("notification_config")

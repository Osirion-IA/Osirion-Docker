"""table hikcentral_config (infos de connexion saisies depuis l'UI)

Ligne unique (singleton). Les 4 infos de connexion HikCentral peuvent être saisies
depuis Paramètres au lieu du seul .env. App Secret chiffré (Fernet). Priorité base
> .env ; table vide = repli .env (aucune régression).

Revision ID: d3e4f5a6b7c8
Revises: c2d3e4f5a6b7
Create Date: 2026-07-21
"""
from alembic import op
import sqlalchemy as sa

revision = "d3e4f5a6b7c8"
down_revision = "c2d3e4f5a6b7"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "hikcentral_config",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("host", sa.String(length=255), nullable=True),
        sa.Column("app_key", sa.String(length=255), nullable=True),
        sa.Column("app_secret_enc", sa.String(length=1024), nullable=True),
        sa.Column("user_id", sa.String(length=128), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
    )


def downgrade():
    op.drop_table("hikcentral_config")

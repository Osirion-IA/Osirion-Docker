"""add blacklist fields on people (watchlist personnes)

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-06-09 00:00:00.000000

Migration ADDITIVE et sûre : ajoute deux colonnes nullable / à défaut sur la table
`people`. Les lignes existantes prennent is_blacklisted=FALSE (server_default) et
blacklist_reason=NULL → aucune donnée existante n'est modifiée ni perdue.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, Sequence[str], None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema — colonnes blacklist sur people."""
    op.add_column(
        'people',
        sa.Column('is_blacklisted', sa.Boolean(), nullable=False, server_default=sa.text('FALSE')),
    )
    op.add_column(
        'people',
        sa.Column('blacklist_reason', sa.String(length=255), nullable=True),
    )
    op.create_index('ix_people_is_blacklisted', 'people', ['is_blacklisted'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_people_is_blacklisted', table_name='people')
    op.drop_column('people', 'blacklist_reason')
    op.drop_column('people', 'is_blacklisted')

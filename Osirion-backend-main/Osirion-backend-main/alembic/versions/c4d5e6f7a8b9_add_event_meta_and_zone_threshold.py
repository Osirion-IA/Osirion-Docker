"""add event.meta (JSON) and zone.threshold (Event Engine — Phase C)

Additif : contexte structuré des événements (zone_id, count, direction…) + seuil
d'attroupement par zone. Aucune donnée existante modifiée.

Revision ID: c4d5e6f7a8b9
Revises: b3c4d5e6f7a8
Create Date: 2026-07-18 12:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c4d5e6f7a8b9'
down_revision: Union[str, Sequence[str], None] = 'b3c4d5e6f7a8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('event', sa.Column('meta', sa.JSON(), nullable=True))
    op.add_column('zone', sa.Column('threshold', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('zone', 'threshold')
    op.drop_column('event', 'meta')

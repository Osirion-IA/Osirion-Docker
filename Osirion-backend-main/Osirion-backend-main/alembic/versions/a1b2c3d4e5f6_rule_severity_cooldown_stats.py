"""professionnalisation du moteur de règles : sévérité, cooldown, observabilité

Additif (aucune donnée existante perdue) :
- rule.severity      : "info" | "warning" | "critical" → routage & couleur UI.
- rule.cooldown_s    : anti-spam — délai mini entre deux déclenchements d'une même
                       règle sur une même zone (0 = pas de temporisation).
- rule.last_triggered_at / rule.trigger_count : observabilité (« déclenchée 12× »).
- alert.severity     : reprise de la sévérité de la règle au moment du déclenchement.

Revision ID: a1b2c3d4e5f6
Revises: d5e6f7a8b9c0
Create Date: 2026-07-19 12:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'd5e6f7a8b9c0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('rule', sa.Column('severity', sa.String(length=20), nullable=False, server_default='warning'))
    op.add_column('rule', sa.Column('cooldown_s', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('rule', sa.Column('last_triggered_at', sa.DateTime(), nullable=True))
    op.add_column('rule', sa.Column('trigger_count', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('alert', sa.Column('severity', sa.String(length=20), nullable=False, server_default='warning'))


def downgrade() -> None:
    op.drop_column('alert', 'severity')
    op.drop_column('rule', 'trigger_count')
    op.drop_column('rule', 'last_triggered_at')
    op.drop_column('rule', 'cooldown_s')
    op.drop_column('rule', 'severity')

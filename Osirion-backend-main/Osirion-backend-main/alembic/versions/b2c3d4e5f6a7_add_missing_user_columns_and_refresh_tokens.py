"""add missing user columns and refresh_tokens

Revision ID: b2c3d4e5f6a7
Revises: 49757c1da997
Create Date: 2025-04-26 00:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, Sequence[str], None] = '49757c1da997'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('user', sa.Column('role', sa.String(length=20), nullable=False, server_default='viewer'))
    op.add_column('user', sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('TRUE')))
    op.add_column('user', sa.Column('is_verified', sa.Boolean(), nullable=False, server_default=sa.text('FALSE')))
    op.add_column('user', sa.Column('updated_at', sa.DateTime(), nullable=True))
    op.add_column('user', sa.Column('last_login', sa.DateTime(), nullable=True))
    op.add_column('user', sa.Column('failed_login_attempts', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('user', sa.Column('locked_until', sa.DateTime(), nullable=True))

    op.create_index('ix_user_email', 'user', ['email'], unique=True)

    op.create_table(
        'refresh_tokens',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('token', sa.Text(), nullable=False, unique=True),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('is_revoked', sa.Boolean(), nullable=False, server_default=sa.text('FALSE')),
        sa.Column('device_info', sa.String(length=255), nullable=True),
        sa.Column('ip_address', sa.String(length=45), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['user.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_refresh_tokens_token', 'refresh_tokens', ['token'], unique=True)
    op.create_index('ix_refresh_tokens_user_id', 'refresh_tokens', ['user_id'])


def downgrade() -> None:
    op.drop_table('refresh_tokens')
    op.drop_column('user', 'locked_until')
    op.drop_column('user', 'failed_login_attempts')
    op.drop_column('user', 'last_login')
    op.drop_column('user', 'updated_at')
    op.drop_column('user', 'is_verified')
    op.drop_column('user', 'is_active')
    op.drop_column('user', 'role')

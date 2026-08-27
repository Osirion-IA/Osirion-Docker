"""portée des règles par régime horaire

Revision ID: e0f1a2b3c4d5
Revises: d0e1f2a3b4c5
Create Date: 2026-08-26
"""
import sqlalchemy as sa
from alembic import op


revision = "e0f1a2b3c4d5"
down_revision = "d0e1f2a3b4c5"
branch_labels = None
depends_on = None

TABLE = "rule"
COLUMN = "work_schedule_id"
INDEX = "ix_rule_work_schedule_id"
FOREIGN_KEY = "fk_rule_work_schedule"


def _inspector():
    return sa.inspect(op.get_bind())


def upgrade():
    columns = {item["name"] for item in _inspector().get_columns(TABLE)}
    if COLUMN not in columns:
        op.add_column(TABLE, sa.Column(COLUMN, sa.Integer(), nullable=True))
    indexes = {item["name"] for item in _inspector().get_indexes(TABLE)}
    if INDEX not in indexes:
        op.create_index(INDEX, TABLE, [COLUMN])
    foreign_keys = {item["name"] for item in _inspector().get_foreign_keys(TABLE)}
    if FOREIGN_KEY not in foreign_keys:
        op.create_foreign_key(
            FOREIGN_KEY, TABLE, "work_schedule", [COLUMN], ["id"], ondelete="CASCADE"
        )


def downgrade():
    foreign_keys = {item["name"] for item in _inspector().get_foreign_keys(TABLE)}
    if FOREIGN_KEY in foreign_keys:
        op.drop_constraint(FOREIGN_KEY, TABLE, type_="foreignkey")
    indexes = {item["name"] for item in _inspector().get_indexes(TABLE)}
    if INDEX in indexes:
        op.drop_index(INDEX, table_name=TABLE)
    columns = {item["name"] for item in _inspector().get_columns(TABLE)}
    if COLUMN in columns:
        op.drop_column(TABLE, COLUMN)

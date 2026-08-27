"""effectif agents par caméra

Ajoute une politique d'effectif à la caméra : capacité nominale, minimum requis,
délai avant signal et régime horaire. Le comptage effectif est réalisé par le
Core sur l'union des zones ``presence`` actives de la caméra.

Revision ID: d0e1f2a3b4c5
Revises: c0d1e2f3a4b5
Create Date: 2026-08-20
"""
import sqlalchemy as sa
from alembic import op


revision = "d0e1f2a3b4c5"
down_revision = "c0d1e2f3a4b5"
branch_labels = None
depends_on = None

TABLE = "camera"


def _inspector():
    return sa.inspect(op.get_bind())


def _columns() -> set[str]:
    return {column["name"] for column in _inspector().get_columns(TABLE)}


def upgrade():
    columns = _columns()
    if "staffing_max_agents" not in columns:
        op.add_column(TABLE, sa.Column("staffing_max_agents", sa.Integer(), nullable=True))
    if "staffing_min_agents" not in columns:
        op.add_column(TABLE, sa.Column("staffing_min_agents", sa.Integer(), nullable=True))
    if "staffing_tolerance_s" not in columns:
        op.add_column(
            TABLE,
            sa.Column(
                "staffing_tolerance_s", sa.Integer(), nullable=False, server_default="300"
            ),
        )
    if "staffing_work_schedule_id" not in columns:
        op.add_column(
            TABLE, sa.Column("staffing_work_schedule_id", sa.Integer(), nullable=True)
        )
        op.create_index(
            "ix_camera_staffing_work_schedule_id",
            TABLE,
            ["staffing_work_schedule_id"],
        )
        op.create_foreign_key(
            "fk_camera_staffing_work_schedule",
            TABLE,
            "work_schedule",
            ["staffing_work_schedule_id"],
            ["id"],
            ondelete="SET NULL",
        )

    # Contraintes défensives : l'API les valide déjà, la base protège aussi les
    # imports/scripts directs.
    constraints = {item["name"] for item in _inspector().get_check_constraints(TABLE)}
    if "ck_camera_staffing_max_agents" not in constraints:
        op.create_check_constraint(
            "ck_camera_staffing_max_agents",
            TABLE,
            "staffing_max_agents IS NULL OR staffing_max_agents BETWEEN 1 AND 500",
        )
    if "ck_camera_staffing_min_agents" not in constraints:
        op.create_check_constraint(
            "ck_camera_staffing_min_agents",
            TABLE,
            "staffing_min_agents IS NULL OR staffing_min_agents BETWEEN 1 AND 500",
        )
    if "ck_camera_staffing_min_le_max" not in constraints:
        op.create_check_constraint(
            "ck_camera_staffing_min_le_max",
            TABLE,
            "staffing_min_agents IS NULL OR staffing_max_agents IS NULL "
            "OR staffing_min_agents <= staffing_max_agents",
        )
    if "ck_camera_staffing_tolerance" not in constraints:
        op.create_check_constraint(
            "ck_camera_staffing_tolerance",
            TABLE,
            "staffing_tolerance_s BETWEEN 30 AND 28800",
        )


def downgrade():
    constraints = {item["name"] for item in _inspector().get_check_constraints(TABLE)}
    for name in (
        "ck_camera_staffing_tolerance",
        "ck_camera_staffing_min_le_max",
        "ck_camera_staffing_min_agents",
        "ck_camera_staffing_max_agents",
    ):
        if name in constraints:
            op.drop_constraint(name, TABLE, type_="check")

    columns = _columns()
    if "staffing_work_schedule_id" in columns:
        foreign_keys = {item["name"] for item in _inspector().get_foreign_keys(TABLE)}
        if "fk_camera_staffing_work_schedule" in foreign_keys:
            op.drop_constraint("fk_camera_staffing_work_schedule", TABLE, type_="foreignkey")
        indexes = {item["name"] for item in _inspector().get_indexes(TABLE)}
        if "ix_camera_staffing_work_schedule_id" in indexes:
            op.drop_index("ix_camera_staffing_work_schedule_id", table_name=TABLE)
        op.drop_column(TABLE, "staffing_work_schedule_id")
    for column in ("staffing_tolerance_s", "staffing_min_agents", "staffing_max_agents"):
        if column in _columns():
            op.drop_column(TABLE, column)

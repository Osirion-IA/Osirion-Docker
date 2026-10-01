"""régimes horaires + zone.work_schedule_id (surveillance de présence aux postes)

Introduit `work_schedule` : jours, créneaux de travail, FUSEAU et tolérance
d'absence d'un groupe d'agences. Une zone de type `presence` pointe vers un
régime ; modifier le régime s'applique aussitôt à toutes ses zones.

Le fuseau appartient au régime et non à la configuration globale : le parc est à
cheval sur UTC+0 (Ghana, Togo, Mali) et UTC+1 (Niger, Bénin). Un décalage global
unique décalerait d'une heure les horaires de la moitié des agences.

FK ON DELETE SET NULL : supprimer un régime ne doit pas emporter les zones — le
poste reste tracé, il cesse simplement d'être surveillé.

Revision ID: c0d1e2f3a4b5
Revises: b9c0d1e2f3a4
Create Date: 2026-08-20
"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "c0d1e2f3a4b5"
down_revision = "b9c0d1e2f3a4"
branch_labels = None
depends_on = None

TABLE = "work_schedule"
COLUMN = "work_schedule_id"
FK_NAME = "fk_zone_work_schedule"


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(name: str) -> bool:
    return name in _inspector().get_table_names()


def _has_column(table: str, col: str) -> bool:
    return col in {c["name"] for c in _inspector().get_columns(table)}


def upgrade():
    # Idempotent : le schéma peut déjà exister sur un environnement neuf créé par
    # SQLModel.metadata.create_all.
    if not _has_table(TABLE):
        op.create_table(
            TABLE,
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("name", sa.String(length=100), nullable=False),
            sa.Column("description", sa.String(length=255), nullable=True),
            sa.Column("timezone", sa.String(length=64), nullable=False,
                      server_default="Africa/Niamey"),
            # {"0": [["08:00","12:00"], …], …} — heures LOCALES au fuseau.
            sa.Column("segments", sa.JSON(), nullable=False),
            sa.Column("absence_tolerance_s", sa.Integer(), nullable=False,
                      server_default="600"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_work_schedule_name", TABLE, ["name"], unique=True)

    if not _has_column("zone", COLUMN):
        op.add_column("zone", sa.Column(COLUMN, sa.Integer(), nullable=True))
        op.create_index("ix_zone_work_schedule_id", "zone", [COLUMN])
        op.create_foreign_key(
            FK_NAME, "zone", TABLE, [COLUMN], ["id"], ondelete="SET NULL",
        )


def downgrade():
    if _has_column("zone", COLUMN):
        op.drop_constraint(FK_NAME, "zone", type_="foreignkey")
        op.drop_index("ix_zone_work_schedule_id", table_name="zone")
        op.drop_column("zone", COLUMN)
    if _has_table(TABLE):
        op.drop_index("ix_work_schedule_name", table_name=TABLE)
        op.drop_table(TABLE)

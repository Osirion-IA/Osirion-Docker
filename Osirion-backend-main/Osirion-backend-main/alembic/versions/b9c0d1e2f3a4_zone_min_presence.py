"""zone.min_presence_s : délai de confirmation de présence

Jusqu'ici l'appartenance à une zone était purement géométrique et INSTANTANÉE :
une personne qui traverse le polygone, ou s'y arrête une seconde, était comptée
comme présente. Elle gonflait l'occupation écrite en base et pouvait déclencher
de faux attroupements (CROWD_MIN_SECONDS porte sur le compte AGRÉGÉ : un flux
continu de passants différents maintient le seuil sans que personne s'arrête).

Cette colonne porte le délai (s) pendant lequel une personne doit rester SANS
INTERRUPTION dans la zone avant d'y être comptée.
  - NULL : la zone suit le défaut Core (ZONE_MIN_PRESENCE_SECONDS, 5 s).
  - 0    : comptage IMMÉDIAT — à réserver aux zones d'intrusion, où tout délai
           serait une régression de sécurité.

Nullable sans valeur par défaut serveur : le repli est décidé côté Core, ce qui
permet de retoucher le comportement de tout le parc via une seule variable
d'environnement, sans UPDATE en base.

Revision ID: b9c0d1e2f3a4
Revises: a8b9c0d1e2f3
Create Date: 2026-08-20
"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "b9c0d1e2f3a4"
down_revision = "a8b9c0d1e2f3"
branch_labels = None
depends_on = None

TABLE = "zone"
COLUMN = "min_presence_s"


def _has_column() -> bool:
    bind = op.get_bind()
    return COLUMN in {c["name"] for c in sa.inspect(bind).get_columns(TABLE)}


def upgrade():
    # Idempotent : la colonne peut déjà exister si le schéma a été créé par
    # SQLModel.metadata.create_all sur un environnement neuf.
    if not _has_column():
        op.add_column(TABLE, sa.Column(COLUMN, sa.Float(), nullable=True))


def downgrade():
    if _has_column():
        op.drop_column(TABLE, COLUMN)

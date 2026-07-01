
# alembic/env.py
import os
from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from sqlmodel import SQLModel
from alembic import context
from dotenv import load_dotenv

# charge le .env
load_dotenv()

# importer ici tous tes modules de modèles SQLModel
# adapte ces imports au nom et emplacement de tes fichiers
from app.models.users import User
from app.models.people import People, PersonEmbedding
from app.models.cameras import Camera
from app.models.events import Event
from app.models.vehicles import Vehicle
from app.models.alerts import Alert
from app.models.audit import AuditLog

# this is the Alembic Config object
config = context.config

# Logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# target metadata for 'autogenerate'
target_metadata = SQLModel.metadata

# lire DATABASE_URL depuis .env
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL not set in .env")

# override sqlalchemy.url from .env for safety
config.set_main_option("sqlalchemy.url", DATABASE_URL)


def run_migrations_offline():
    context.configure(
        url=DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()


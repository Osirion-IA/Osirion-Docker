from sqlmodel import SQLModel, create_engine, Session
from decouple import config

# URL PostgreSQL
DATABASE_URL = config("DATABASE_URL")

# echo=True pour voir les requêtes SQL dans la console
engine = create_engine(DATABASE_URL, echo=False)

# Créer les tables (optionnel si tu utilises Alembic)
#def create_db_and_tables():
 #   SQLModel.metadata.create_all(engine)

# Session locale
def get_session():
    with Session(engine) as session:
        yield session


def create_engine_and_session():
    engine = create_engine(DATABASE_URL, echo=True)
    session = Session(engine)
    return engine, session

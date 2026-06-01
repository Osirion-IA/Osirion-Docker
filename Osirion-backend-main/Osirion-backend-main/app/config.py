from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # DATABASE
    DATABASE_URL: str = "postgresql+psycopg2://postgres:password@db:5432/Osirion-AI"
    
    # JWT AUTHENTICATION
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    FERNET_KEY: str  # Doit être une clé Fernet valide
    
    # SECURITY
    BCRYPT_ROUNDS: int = 12
    
    # CORS
    BACKEND_CORS_ORIGINS: list[str] = ["*"]  # à changer en prod pour ton frontend

    # AI / Embeddings
    EMBEDDING_DIM: int = 512

    # RATE LIMITING
    RATE_LIMIT_PER_MINUTE: str = "5/minute"  # pour les routes sensibles (login)
    RATE_LIMIT_GENERAL: str = "100/minute"   # pour les routes générales

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

# Instance globale
settings = Settings()
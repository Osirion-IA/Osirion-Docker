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

    # DECISION ENGINE — décalage horaire (heures) appliqué à l'évaluation des
    # plages horaires des règles (les timestamps sont en UTC). Ex. +1 pour l'heure
    # d'Europe centrale. 0 = plages interprétées en UTC.
    RULE_TZ_OFFSET_HOURS: int = 0

    # RATE LIMITING
    RATE_LIMIT_PER_MINUTE: str = "5/minute"  # pour les routes sensibles (login)
    RATE_LIMIT_GENERAL: str = "100/minute"   # pour les routes générales

    # NOTIFICATIONS D'ALERTE — déclenchées MANUELLEMENT par un utilisateur
    # (POST /alerts/{id}/notify), jamais en automatique. Tous optionnels : si non
    # renseignés, l'endpoint /notify renvoie une erreur claire (pas de crash).
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = "osirion@localhost"
    SMTP_USE_TLS: bool = True
    ALERT_EMAIL_TO: str = ""        # destinataire(s) par défaut, séparés par des virgules
    ALERT_WEBHOOK_URL: str = ""     # webhook POST JSON (Slack/Teams/endpoint custom)

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

# Instance globale
settings = Settings()
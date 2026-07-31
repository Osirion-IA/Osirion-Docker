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

    # AUTH MACHINE-À-MACHINE (Core) — clé de service statique, SANS expiration.
    # Le Core (service interne) s'authentifie via l'en-tête X-API-Key au lieu d'un
    # JWT : plus de login/refresh/expiration → il ne se déconnecte jamais. Vide =
    # désactivé (le Core retombe alors sur l'auth JWT email/password classique).
    # À définir dans .env (secret long, généré aléatoirement). Réseau interne Docker.
    CORE_API_KEY: str = ""
    
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

    # SOURCE DE FLUX HIKCENTRAL (OpenAPI Gateway Artemis, AK/SK) — optionnel.
    # Si renseigné, on peut synchroniser le catalogue de caméras (par groupe/area)
    # et résoudre des URLs RTSP standard (rtsp_s). Vide = connecteur désactivé.
    HIK_HOST: str = ""              # ex. https://137.74.118.35:443 (OpenAPI Gateway)
    HIK_APP_KEY: str = ""           # Integration Partner Key
    HIK_APP_SECRET: str = ""        # Integration Partner Secret
    HIK_USER_ID: str = ""           # Linked User du partner
    HIK_VERIFY_SSL: bool = False    # certif auto-signé → False en dev
    HIK_STREAM_TYPE: int = 1        # 0=main (HEVC 1440p), 1=sub (HEVC 360p, léger) → ingestion
    # Synchronisation périodique du catalogue (thread de fond). 0 = désactivée
    # (synchro manuelle seulement, via POST /hikcentral/sync).
    HIK_SYNC_INTERVAL_MINUTES: int = 15

    # ── Historique de connectivité caméra (poller backend → camera_status_event) ──
    # Le backend interroge la santé du Core et persiste les transitions d'état.
    CORE_URL: str = "http://core:5000"           # URL interne Docker du Core
    CAMERA_STATUS_POLL_SECONDS: int = 15
    CAMERA_STATUS_RECORDER_ENABLED: bool = True

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

# Instance globale
settings = Settings()
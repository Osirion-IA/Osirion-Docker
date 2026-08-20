# app/models/notification_config.py
"""
Configuration des NOTIFICATIONS (email SMTP + webhook) saisie depuis l'interface
(Paramètres → Notifications).

Ligne unique (singleton, id=1). Le mot de passe SMTP est CHIFFRÉ au repos (Fernet)
et jamais renvoyé en clair. Priorité : si cette ligne est renseignée, elle PRIME
sur le .env ; sinon repli sur les variables d'environnement (aucune régression
pour l'existant). Même pattern que hikcentral_config.
"""
from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import datetime


class NotificationConfig(SQLModel, table=True):
    __tablename__ = "notification_config"

    id: Optional[int] = Field(default=1, primary_key=True)   # singleton
    smtp_host: Optional[str] = Field(default=None, max_length=255)
    smtp_port: Optional[int] = Field(default=None)
    smtp_user: Optional[str] = Field(default=None, max_length=255)
    # Mot de passe SMTP CHIFFRÉ (Fernet) — jamais stocké ni renvoyé en clair.
    smtp_password_enc: Optional[str] = Field(default=None, max_length=1024)
    smtp_from: Optional[str] = Field(default=None, max_length=255)
    smtp_use_tls: Optional[bool] = Field(default=None)
    alert_email_to: Optional[str] = Field(default=None, max_length=1024)   # liste séparée par des virgules
    alert_webhook_url: Optional[str] = Field(default=None, max_length=1024)

    updated_at: Optional[datetime] = Field(default=None)
    updated_by: Optional[str] = Field(default=None, max_length=255)   # email de l'admin

# app/models/hikcentral_config.py
"""
Configuration de CONNEXION HikCentral saisie depuis l'interface (Paramètres).

Ligne unique (singleton, id=1). Ne contient que les **informations de connexion**
non techniques : hôte (gateway), App Key, App Secret (CHIFFRÉ au repos, Fernet) et
Linked User. Les paramètres techniques (verify_ssl, stream_type, transcodage,
intervalle de synchro) restent côté .env/settings.

Priorité : si cette ligne est renseignée, elle PRIME sur le .env ; sinon on retombe
sur les variables d'environnement (repli → aucune régression pour l'existant).
"""
from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import datetime


class HikCentralConfig(SQLModel, table=True):
    __tablename__ = "hikcentral_config"

    id: Optional[int] = Field(default=1, primary_key=True)   # singleton
    host: Optional[str] = Field(default=None, max_length=255)
    app_key: Optional[str] = Field(default=None, max_length=255)
    # App Secret CHIFFRÉ (Fernet) — jamais stocké ni renvoyé en clair.
    app_secret_enc: Optional[str] = Field(default=None, max_length=1024)
    user_id: Optional[str] = Field(default=None, max_length=128)

    updated_at: Optional[datetime] = Field(default=None)
    updated_by: Optional[str] = Field(default=None, max_length=255)   # email de l'admin

from slowapi import Limiter
from slowapi.util import get_remote_address
from fastapi import Request

# Initialisation du limiteur de taux
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200/minute"]  # Limite par défaut
)

# Fonctions helper pour obtenir les clés de rate limiting personnalisées

def get_user_email(request: Request) -> str:
    """
    Récupère l'email de l'utilisateur depuis le corps de la requête.
    Utilisé pour limiter les tentatives de connexion par email.
    """
    try:
        # Pour les routes qui utilisent un formulaire JSON
        if hasattr(request.state, "email"):
            return request.state.email
        return get_remote_address(request)
    except:
        return get_remote_address(request)


def get_ip_or_user(request: Request) -> str:
    """
    Retourne l'IP ou l'identifiant utilisateur pour le rate limiting.
    Priorité : user_id si authentifié, sinon IP.
    """
    try:
        if hasattr(request.state, "user_id"):
            return f"user:{request.state.user_id}"
        return get_remote_address(request)
    except:
        return get_remote_address(request)


# Configuration de rate limits spécifiques
RATE_LIMITS = {
    "login": "5/minute",          # Limite stricte pour les tentatives de connexion
    "register": "3/hour",         # Limite pour les inscriptions
    "password_reset": "3/hour",   # Limite pour les demandes de reset de mot de passe
    "token_refresh": "10/minute", # Limite pour le rafraîchissement de tokens
    "general_api": "100/minute",  # Limite générale pour l'API
    "search": "30/minute",        # Limite pour les recherches
    "upload": "10/minute",        # Limite pour les uploads
}
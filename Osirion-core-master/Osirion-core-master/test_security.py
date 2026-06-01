"""
Script de test de sécurité - Osirion Core
Vérifie que les configurations de sécurité sont correctement appliquées
"""
import os
import sys
sys.path.append(os.getcwd())

from dotenv import load_dotenv
from config import settings

def test_security_config():
    """Teste les configurations de sécurité"""
    print("=" * 60)
    print("🔒 TEST DE SÉCURITÉ - OSIRION-CORE")
    print("=" * 60)
    
    # Test 1 : Secret Flask
    print("\n[TEST 1] Secret Flask...")
    if settings.FLASK_SECRET_KEY:
        secret_length = len(settings.FLASK_SECRET_KEY)
        if secret_length >= 32:
            print(f"✅ Secret défini ({secret_length} caractères)")
            # Vérifier que ce n'est pas le secret par défaut hardcodé
            if settings.FLASK_SECRET_KEY == 'osirion-surveillance-2026':
                print("⚠️  ATTENTION : Secret par défaut détecté (peu sécurisé)")
            else:
                print("✅ Secret personnalisé détecté")
        else:
            print(f"⚠️  Secret trop court ({secret_length} caractères, minimum 32)")
    else:
        print("❌ Aucun secret défini")
    
    # Test 2 : CORS
    print("\n[TEST 2] Configuration CORS...")
    cors_origins = settings.CORS_ALLOWED_ORIGINS
    print(f"Origines autorisées : {cors_origins}")
    
    if cors_origins == ['*']:
        print("⚠️  CORS ouvert à tous (OK en développement, DANGEREUX en production)")
        print("    Recommandation : Définir CORS_ALLOWED_ORIGINS dans .env")
    else:
        print(f"✅ CORS restreint à {len(cors_origins)} origine(s)")
        for origin in cors_origins:
            if origin.startswith('https://'):
                print(f"   ✅ {origin} (HTTPS - sécurisé)")
            elif origin.startswith('http://localhost') or origin.startswith('http://127.0.0.1'):
                print(f"   ⚠️  {origin} (local - OK pour dev)")
            else:
                print(f"   ⚠️  {origin} (HTTP - non sécurisé)")
    
    # Test 3 : Variables d'environnement
    print("\n[TEST 3] Variables d'environnement...")
    load_dotenv()
    
    required_vars = {
        'API_URL': os.getenv('API_URL'),
        'AUTH_EMAIL': os.getenv('AUTH_EMAIL'),
        'AUTH_PASSWORD': os.getenv('AUTH_PASSWORD'),
        'FLASK_SECRET_KEY': os.getenv('FLASK_SECRET_KEY')
    }
    
    for var_name, var_value in required_vars.items():
        if var_value:
            if var_name == 'AUTH_PASSWORD':
                print(f"✅ {var_name} : ******** (masqué)")
            elif var_name == 'FLASK_SECRET_KEY':
                print(f"✅ {var_name} : {var_value[:16]}... ({len(var_value)} chars)")
            else:
                print(f"✅ {var_name} : {var_value}")
        else:
            print(f"⚠️  {var_name} : Non défini")
    
    # Test 4 : Configuration streaming
    print("\n[TEST 4] Configuration streaming...")
    print(f"Host : {settings.WEB_STREAMING_HOST}")
    print(f"Port : {settings.WEB_STREAMING_PORT}")
    print(f"JPEG Quality : {settings.JPEG_QUALITY}%")
    
    if settings.WEB_STREAMING_HOST == '0.0.0.0':
        print("⚠️  Server écoute sur toutes les interfaces (0.0.0.0)")
        print("    Recommandation production : Limiter à une interface spécifique")
    
    # Recommandations finales
    print("\n" + "=" * 60)
    print("📋 RECOMMANDATIONS")
    print("=" * 60)
    
    recommendations = []
    
    if cors_origins == ['*']:
        recommendations.append("🔴 CRITIQUE : Restreindre CORS en production")
    
    if os.getenv('debug', 'False').lower() == 'true':
        recommendations.append("🟡 IMPORTANT : Désactiver debug=False en production")
    
    if settings.FLASK_SECRET_KEY and len(settings.FLASK_SECRET_KEY) < 64:
        recommendations.append("🟢 CONSEIL : Utiliser un secret de 64+ caractères")
    
    if not any(origin.startswith('https://') for origin in cors_origins if origin != '*'):
        recommendations.append("🟡 IMPORTANT : Activer HTTPS en production")
    
    if recommendations:
        for rec in recommendations:
            print(f"  {rec}")
    else:
        print("  ✅ Configuration de sécurité optimale !")
    
    print("\n" + "=" * 60)
    print("Test de sécurité terminé")
    print("=" * 60)


if __name__ == "__main__":
    try:
        test_security_config()
    except Exception as e:
        print(f"\n❌ Erreur lors du test : {e}")
        import traceback
        traceback.print_exc()

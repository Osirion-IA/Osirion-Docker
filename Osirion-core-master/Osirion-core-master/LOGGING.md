# 📝 Système de Logging Structuré - Osirion-Core

## ✅ Améliorations implémentées

### 1. **Module de logging centralisé** ([utils/logger.py](utils/logger.py))

#### Fonctionnalités :
- ✅ **Logs structurés en JSON** (optionnel) pour parsing automatique
- ✅ **Rotation automatique des fichiers** (10 MB par défaut, 5 backups)
- ✅ **4 types de fichiers de logs** :
  - `logs/osirion.log` - Tous les logs (texte lisible)
  - `logs/osirion.json.log` - Logs JSON structurés (si activé)
  - `logs/osirion.error.log` - Erreurs uniquement (ERROR et CRITICAL)
  - Logs automatiques avec horodatage
- ✅ **Affichage console coloré** pour développement
- ✅ **Contexte enrichi** (camera_id, track_id, fps, latency, etc.)

#### Utilisation :
```python
from utils.logger import get_logger

logger = get_logger(__name__)

# Log simple
logger.info("Caméra connectée")

# Log avec contexte structuré
logger.info(
    "Reconnaissance faciale détectée",
    extra={
        'camera_id': 1,
        'person_name': 'John Doe',
        'recognition_score': 0.95
    }
)

# Log d'erreur avec stack trace
try:
    # code
except Exception as e:
    logger.error("Erreur traitement frame", exc_info=True)
```

---

### 2. **Remplacement complet des print()**

Tous les `print()` ont été remplacés par des appels logger appropriés dans :

- ✅ [core/surveillance_system.py](core/surveillance_system.py)
- ✅ [core/camera_manager.py](core/camera_manager.py)
- ✅ [core/tracking_processor.py](core/tracking_processor.py)
- ✅ [core/web_streaming.py](core/web_streaming.py)
- ✅ [services/camera_fetching_service.py](services/camera_fetching_service.py)
- ✅ [services/embeddings_search_service.py](services/embeddings_search_service.py)
- ✅ [utils/auth_utils.py](utils/auth_utils.py)
- ✅ [main_refactored.py](main_refactored.py)

---

### 3. **Configuration via variables d'environnement**

Ajout dans [config/settings.py](config/settings.py) :

```python
LOG_LEVEL = 'INFO'              # DEBUG, INFO, WARNING, ERROR, CRITICAL
LOG_DIR = 'logs'                # Répertoire des logs
ENABLE_JSON_LOGS = False        # Logs JSON (production)
ENABLE_CONSOLE_LOGS = True      # Affichage console (développement)
LOG_MAX_BYTES = 10 * 1024 * 1024  # 10 MB avant rotation
LOG_BACKUP_COUNT = 5            # Nombre de backups
```

Ces paramètres peuvent être définis dans `.env` :
```env
LOG_LEVEL=INFO
LOG_DIR=logs
ENABLE_JSON_LOGS=false
ENABLE_CONSOLE_LOGS=true
LOG_MAX_BYTES=10485760
LOG_BACKUP_COUNT=5
```

---

### 4. **Initialisation dans main_refactored.py**

```python
from utils.logger import setup_logging, get_logger

# Initialiser le système de logging au démarrage
setup_logging(
    log_level=settings.LOG_LEVEL,
    log_dir=settings.LOG_DIR,
    enable_json=settings.ENABLE_JSON_LOGS,
    enable_console=settings.ENABLE_CONSOLE_LOGS,
    max_bytes=settings.LOG_MAX_BYTES,
    backup_count=settings.LOG_BACKUP_COUNT
)

logger = get_logger(__name__)
logger.info("Démarrage d'Osirion-Core...")
```

---

## 📊 Niveaux de logging utilisés

| Niveau | Usage | Exemples |
|--------|-------|----------|
| **DEBUG** | Détails techniques | Thread démarré, frames envoyées |
| **INFO** | Événements normaux | Caméra connectée, reconnaissance réussie |
| **WARNING** | Situations anormales non critiques | Échecs de connexion, reconnexion |
| **ERROR** | Erreurs nécessitant attention | Erreur API, échec traitement |
| **CRITICAL** | Défaillances système | Impossible de démarrer |

---

## 🎯 Avantages du système de logging

### En développement :
- ✅ **Console colorée** facile à lire
- ✅ **Contexte enrichi** pour déboguer (camera_id, track_id, etc.)
- ✅ **Fichiers de logs** persistants

### En production :
- ✅ **Logs JSON structurés** pour parsing automatique
- ✅ **Rotation automatique** des fichiers (pas de disque plein)
- ✅ **Fichier d'erreurs séparé** pour alerting
- ✅ **Compatible ELK, Loki, CloudWatch** pour centralisation

---

## 📦 Intégration avec outils externes

### Elasticsearch + Kibana (ELK Stack)
```bash
# Activer les logs JSON
ENABLE_JSON_LOGS=true

# Envoyer les logs vers Logstash
filebeat -c filebeat.yml
```

### Prometheus + Grafana
```python
# Ajouter des métriques custom
from prometheus_client import Counter

face_recognitions = Counter('face_recognitions_total', 'Total recognitions')
face_recognitions.inc()
```

### Sentry pour erreurs
```python
import sentry_sdk

sentry_sdk.init(dsn="votre-dsn")
logger.error("Erreur critique", exc_info=True)  # Auto-envoyé à Sentry
```

---

## 🚀 Prochaines étapes recommandées

1. **Health check endpoint** avec logging
2. **Métriques de performance** (FPS, latence, mémoire)
3. **Alerting** sur erreurs critiques (PagerDuty, Slack)
4. **Dashboard** de monitoring (Grafana)

---

## 📝 Exemple de sortie console

```
[2026-02-03 14:30:15] INFO     [__main__] Démarrage d'Osirion-Core...
[2026-02-03 14:30:15] INFO     [utils.auth_utils] Initialisation du module d'authentification...
[2026-02-03 14:30:16] INFO     [utils.auth_utils] Connexion réussie à l'API
[2026-02-03 14:30:16] INFO     [services.camera_fetching_service] 3 caméra(s) récupérée(s) depuis l'API
[2026-02-03 14:30:16] INFO     [core.surveillance_system] Caméras actives : ['Entrée (id=1, Hall)', 'Parking (id=2, Extérieur)']
[2026-02-03 14:30:17] INFO     [core.camera_manager] Caméra 1 (Entrée) connectée avec succès
[2026-02-03 14:30:20] INFO     [core.tracking_processor] Reconnaissance faciale : Alice Dupont (score 0.95)
[2026-02-03 14:30:25] WARNING  [core.camera_manager] Caméra 2 : 5 échecs consécutifs, reconnexion...
```

---

## 📋 Format des logs JSON

```json
{
  "timestamp": "2026-02-03T14:30:20.123456Z",
  "level": "INFO",
  "logger": "core.tracking_processor",
  "message": "Reconnaissance faciale : Alice Dupont (score 0.95)",
  "module": "tracking_processor",
  "function": "update_person_database",
  "line": 125,
  "camera_id": 1,
  "camera_name": "Entrée",
  "location": "Hall",
  "track_id": 42,
  "person_name": "Alice Dupont",
  "recognition_score": 0.95
}
```

Ce format permet de :
- Indexer dans Elasticsearch
- Filtrer par camera_id, track_id, etc.
- Créer des dashboards Kibana/Grafana
- Alerter sur des patterns spécifiques

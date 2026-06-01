# 🎥 OSIRION-CORE

**Système de surveillance multi-caméras avec reconnaissance faciale en temps réel**

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Status](https://img.shields.io/badge/status-production-brightgreen.svg)](https://github.com)

---

## 📋 Table des matières

- [Vue d'ensemble](#-vue-densemble)
- [Fonctionnalités](#-fonctionnalités)
- [Architecture](#-architecture)
- [Installation](#-installation)
- [Configuration](#-configuration)
- [Utilisation](#-utilisation)
- [API WebSocket](#-api-websocket)
- [Performances](#-performances)
- [Sécurité](#-sécurité)
- [Troubleshooting](#-troubleshooting)
- [Contribution](#-contribution)

---

## 🌟 Vue d'ensemble

Osirion-Core est une solution complète de surveillance vidéo intelligente qui combine :

- **Détection de visages** : YOLO v11n (optimisé CPU)
- **Reconnaissance faciale** : InsightFace buffalo_l
- **Tracking multi-objets** : ByteTrack
- **Streaming temps réel** : WebSocket (Socket.IO)
- **Multi-caméras** : Support illimité de flux RTSP simultanés

### 🎯 Cas d'usage

- Surveillance d'entreprise
- Contrôle d'accès intelligent
- Analyse de flux en magasin
- Sécurité événementielle
- Smart cities

---

## ✨ Fonctionnalités

### 🔍 Détection et reconnaissance

- ✅ Détection faciale haute précision (YOLO v11n)
- ✅ Reconnaissance faciale par embeddings 512D
- ✅ Tracking persistant avec réidentification
- ✅ Cache intelligent (évite reconnaissances répétées)
- ✅ Support multi-visages simultanés

### 📹 Gestion des caméras

- ✅ Connexion RTSP robuste avec reconnexion automatique
- ✅ Backoff exponentiel sur échecs réseau
- ✅ Support multi-caméras illimité
- ✅ Traitement parallèle (2 threads par caméra)
- ✅ Gestion automatique du buffer vidéo

### 🌐 Streaming Web

- ✅ WebSocket faible latence (<250ms)
- ✅ Streaming 30 FPS par caméra
- ✅ Support multi-clients simultanés
- ✅ API REST pour métadonnées
- ✅ Compression JPEG configurable

### 🛡️ Sécurité

- ✅ Authentification JWT avec refresh tokens
- ✅ CORS configurable
- ✅ Secrets externalisés (.env)
- ✅ Session Flask sécurisée
- ✅ Chiffrement HTTPS (recommandé)

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     CLIENT FRONTEND                         │
│  (React / Vue / Angular / HTML+JS)                          │
└────────────────┬────────────────────────────────────────────┘
                 │ WebSocket (Socket.IO)
                 ▼
┌─────────────────────────────────────────────────────────────┐
│              WEB STREAMING SERVER                           │
│  Flask + Flask-SocketIO (port 5000)                         │
│  • Routes REST API                                          │
│  • Gestion WebSocket                                        │
│  • Encodage JPEG + Base64                                   │
└────────────────┬────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────┐
│           SURVEILLANCE SYSTEM (Orchestration)               │
│  • Initialisation caméras                                   │
│  • Gestion threads                                          │
│  • Synchronisation résultats                                │
└────┬───────────────────────────────────────────┬────────────┘
     │                                           │
     ▼                                           ▼
┌──────────────────────┐           ┌──────────────────────────┐
│  CAMERA CAPTURE      │           │  TRACKING PROCESSOR      │
│  Thread par caméra   │           │  Thread par caméra       │
│  • Connexion RTSP    │═══════════│  • Détection YOLO        │
│  • Reconnexion auto  │  Queue    │  • Tracking ByteTrack    │
│  • Buffer gestion    │           │  • Reconnaissance        │
└──────────────────────┘           │  • Annotation frames     │
                                   └────────┬─────────────────┘
                                            │
                                            ▼
                                   ┌─────────────────────┐
                                   │   EXTERNAL API      │
                                   │  • Auth JWT         │
                                   │  • Embeddings DB    │
                                   │  • People search    │
                                   └─────────────────────┘
```

### 📦 Modules

```
osirion-core/
├── config/                 # Configuration centralisée
│   ├── __init__.py
│   └── settings.py        # Toutes les constantes
├── core/                   # Modules principaux
│   ├── __init__.py
│   ├── camera_manager.py  # Gestion RTSP
│   ├── surveillance_system.py  # Orchestrateur
│   ├── tracking_processor.py   # IA + Tracking
│   └── web_streaming.py   # Serveur WebSocket
├── services/              # Services externes
│   ├── camera_fetching_service.py
│   └── embeddings_search_service.py
├── utils/                 # Utilitaires
│   └── auth_utils.py      # Authentification JWT
├── templates/             # Templates HTML
│   └── index.html
├── face_detection.py      # Détection + embeddings
├── main_refactored.py     # Point d'entrée principal
└── requirements.txt       # Dépendances Python
```

---

## 🚀 Installation

### Prérequis

- **Python** : 3.8 ou supérieur
- **GPU** : Optionnel (CUDA pour accélération)
- **RAM** : 4 GB minimum, 8 GB recommandé
- **Bande passante** : 5 Mbps par caméra

### 1. Cloner le dépôt

```bash
git clone https://github.com/votre-org/osirion-core.git
cd osirion-core
```

### 2. Créer un environnement virtuel

```bash
# Windows
python -m venv venv
venv\Scripts\activate

# Linux/Mac
python3 -m venv venv
source venv/bin/activate
```

### 3. Installer les dépendances

```bash
pip install -r requirements.txt
```

#### Dépendances principales manquantes dans requirements.txt

**⚠️ Important** : Ajoutez ces packages manuellement :

```bash
pip install opencv-python
pip install ultralytics
pip install insightface
pip install onnxruntime
pip install lap
pip install python-dotenv
```

### 4. Télécharger les modèles

#### YOLOv11n-face

```bash
# Le modèle se télécharge automatiquement au premier lancement
# Ou téléchargez manuellement depuis Ultralytics Hub
```

#### InsightFace buffalo_l

```bash
# S'installe automatiquement via insightface
# Ou placez les modèles dans ~/.insightface/models/
```

### 5. Configurer l'environnement

```bash
# Copier le template
cp .env.example .env

# Éditer avec vos valeurs
nano .env
```

---

## ⚙️ Configuration

### Fichier `.env`

```bash
# API Backend
API_URL=http://192.168.0.103:8000/
AUTH_EMAIL=votre-email@example.com
AUTH_PASSWORD=votre-mot-de-passe-securise

# Mode debug
debug=False

# Sécurité WebSocket
FLASK_SECRET_KEY=votre-secret-aleatoire-64-caracteres-minimum
CORS_ALLOWED_ORIGINS=https://votre-domaine.com,https://app.votre-domaine.com
```

### Générer un secret Flask sécurisé

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

### Fichier `config/settings.py`

Paramètres principaux ajustables :

```python
# Performance
PROCESS_EVERY_N_FRAME = 10      # Traiter 1 frame sur 10 (ajuster selon CPU)
FRAME_SIZE = (640, 480)         # Résolution de traitement

# Reconnaissance
RECOGNITION_THRESHOLD = 0.70    # Seuil de confiance (0.0-1.0)
REIDENTIFICATION_INTERVAL = 200 # Frames entre réidentifications

# Reconnexion RTSP
MAX_RECONNECTION_ATTEMPTS = 5   # Tentatives avant abandon
RECONNECTION_BASE_DELAY = 1.0   # Délai backoff initial (secondes)

# Streaming
WEB_STREAMING_PORT = 5000       # Port du serveur WebSocket
JPEG_QUALITY = 85               # Qualité compression (50-100)
```

---

## 🎮 Utilisation

### Démarrage rapide

```bash
# Activer l'environnement virtuel
venv\Scripts\activate  # Windows
source venv/bin/activate  # Linux/Mac

# Lancer l'application
python main_refactored.py
```

### Mode développement

```bash
# Avec logs détaillés
DEBUG=True python main_refactored.py

# Sur un port spécifique
WEB_STREAMING_PORT=8080 python main_refactored.py
```

### Sortie attendue

```
Initialisation du module d'authentification...
Connexion à l'API en cours...
Connexion réussie !
Prêt à utiliser l'API !

Caméras trouvées au total : 3
Caméras actives : ['Entrée principale (id=1)', 'Parking (id=2)']
[INFO] Connexion à la caméra 1 (Entrée principale)...
[OK] Caméra 1 (Entrée principale) connectée
Système multi-caméras prêt en mode headless (sans affichage).
[INFO] Serveur de streaming WebSocket démarré sur http://0.0.0.0:5000
Appuyez sur Ctrl+C pour quitter.
```

---

## 🌐 API WebSocket

### Connexion cliente

#### JavaScript (vanilla)

```javascript
const socket = io('http://localhost:5000');

socket.on('cameras_list', (data) => {
    console.log('Caméras disponibles:', data.cameras);
});

socket.emit('start_stream', { camera_id: 1 });

socket.on('frame', (data) => {
    const img = new Image();
    img.src = 'data:image/jpeg;base64,' + data.data;
    document.getElementById('canvas').src = img.src;
});
```

#### React

```jsx
import { useEffect } from 'react';
import io from 'socket.io-client';

function CameraStream({ cameraId }) {
    useEffect(() => {
        const socket = io('http://localhost:5000');
        
        socket.emit('start_stream', { camera_id: cameraId });
        
        socket.on('frame', (data) => {
            // Traitement de la frame
        });
        
        return () => socket.disconnect();
    }, [cameraId]);
}
```

### Événements WebSocket

#### Événements CLIENT → SERVEUR

| Événement | Payload | Description |
|-----------|---------|-------------|
| `start_stream` | `{camera_id: int}` | Démarre le stream d'une caméra |
| `stop_stream` | - | Arrête le stream actuel |

#### Événements SERVEUR → CLIENT

| Événement | Payload | Description |
|-----------|---------|-------------|
| `cameras_list` | `{cameras: [...]}` | Liste des caméras (auto à la connexion) |
| `stream_started` | `{camera_id: int}` | Confirmation démarrage stream |
| `frame` | `{camera_id, data, timestamp}` | Frame encodée en base64 (30/sec) |
| `stream_stopped` | - | Confirmation arrêt stream |
| `error` | `{message: string}` | Erreur survenue |

### API REST

#### GET `/api/cameras`

Liste des caméras disponibles.

**Réponse** :
```json
{
    "cameras": [
        {
            "id": 1,
            "name": "Entrée principale",
            "location": "Hall A",
            "status": "online"
        }
    ],
    "count": 3
}
```

#### GET `/api/stats`

Statistiques du système.

**Réponse** :
```json
{
    "total_cameras": 3,
    "active_streams": 2,
    "uptime": 3600.5
}
```

---

## 📊 Performances

### Capacités système

| Configuration | Caméras max | FPS effectif | Latence |
|---------------|-------------|--------------|---------|
| **CPU Intel i5** (8 threads) | 2-3 | 10-15 | 300-500ms |
| **CPU AMD Ryzen 7** | 4-5 | 15-20 | 250-400ms |
| **GPU NVIDIA RTX 3060** | 10-12 | 20-25 | 180-250ms |
| **GPU NVIDIA RTX 4090** | 20+ | 25-30 | 150-200ms |

### Optimisations

#### CPU

```python
# config/settings.py
PROCESS_EVERY_N_FRAME = 15  # Traiter moins de frames
FRAME_SIZE = (480, 360)     # Réduire la résolution
```

#### GPU (CUDA)

```python
# Modifier face_detection.py
app = FaceAnalysis(
    providers=['CUDAExecutionProvider'],  # GPU au lieu de CPU
    allowed_modules=['detection', 'recognition']
)
app.prepare(ctx_id=0, det_size=(640, 640))  # GPU + résolution élevée
```

### Métriques temps réel

| Opération | Temps CPU | Temps GPU |
|-----------|-----------|-----------|
| Détection YOLO | 150-300ms | 15-30ms |
| Reconnaissance InsightFace | 100-200ms | 10-20ms |
| ByteTrack | 5-10ms | 5-10ms |
| Encodage JPEG | 10-20ms | 10-20ms |
| **Total par frame** | **265-530ms** | **40-80ms** |

---

## 🔒 Sécurité

### ✅ Bonnes pratiques

1. **Secrets externalisés**
   ```bash
   # .env - JAMAIS commit
   FLASK_SECRET_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")
   ```

2. **CORS restreint**
   ```bash
   CORS_ALLOWED_ORIGINS=https://app.example.com
   ```

3. **HTTPS obligatoire**
   ```python
   # Utiliser un reverse proxy (Nginx)
   location /socket.io/ {
       proxy_pass http://localhost:5000;
       proxy_http_version 1.1;
       proxy_set_header Upgrade $http_upgrade;
       proxy_set_header Connection "upgrade";
   }
   ```

4. **Authentification WebSocket** (TODO)
   ```javascript
   const socket = io('http://localhost:5000', {
       auth: { token: 'jwt-token-here' }
   });
   ```

### 🚨 Checklist avant production

- [ ] `FLASK_SECRET_KEY` généré aléatoirement (64+ chars)
- [ ] `CORS_ALLOWED_ORIGINS` restreint aux domaines autorisés
- [ ] `debug=False` dans .env
- [ ] Fichier `.env` dans `.gitignore`
- [ ] HTTPS activé (certificat SSL)
- [ ] Firewall configuré (limiter accès port 5000)
- [ ] Rate limiting implémenté
- [ ] Logs sécurisés (pas de tokens)
- [ ] Monitoring actif (Prometheus/Grafana)

Consultez [SECURITY.md](SECURITY.md) pour plus de détails.

---

## 🐛 Troubleshooting

### Problème : Caméra ne se connecte pas

**Symptômes** :
```
[ERREUR] Caméra 1 : impossible d'ouvrir le flux RTSP
```

**Solutions** :
1. Vérifier l'URL RTSP :
   ```bash
   ffplay rtsp://admin:password@192.168.1.64:554/stream
   ```
2. Tester la connectivité réseau :
   ```bash
   ping 192.168.1.64
   ```
3. Augmenter les timeouts :
   ```python
   MAX_RECONNECTION_ATTEMPTS = 10
   RECONNECTION_BASE_DELAY = 2.0
   ```

### Problème : Performances faibles

**Symptômes** : FPS < 5, latence > 1s

**Solutions** :
1. Réduire le nombre de caméras
2. Augmenter `PROCESS_EVERY_N_FRAME` :
   ```python
   PROCESS_EVERY_N_FRAME = 20  # Au lieu de 10
   ```
3. Diminuer la résolution :
   ```python
   FRAME_SIZE = (480, 360)
   ```
4. Activer le GPU (voir section Optimisations)

### Problème : Reconnaissance inexacte

**Symptômes** : Mauvaises identifications, score < 0.6

**Solutions** :
1. Améliorer la base de données d'embeddings
2. Ajuster le seuil :
   ```python
   RECOGNITION_THRESHOLD = 0.75  # Plus strict
   ```
3. Augmenter `det_size` :
   ```python
   app.prepare(ctx_id=-1, det_size=(640, 640))
   ```

### Problème : WebSocket déconnecté

**Symptômes** : Client se déconnecte fréquemment

**Solutions** :
1. Vérifier le secret Flask (doit être constant)
2. Augmenter le timeout Socket.IO :
   ```javascript
   const socket = io(url, { timeout: 60000 });
   ```
3. Vérifier le firewall/proxy

### Logs utiles

```bash
# Activer les logs détaillés
export DEBUG=True
python main_refactored.py > app.log 2>&1

# Analyser les erreurs
grep -i error app.log
grep -i warn app.log
```

---

## 📚 Documentation complémentaire

- [INTEGRATION_GUIDE.md](INTEGRATION_GUIDE.md) - Intégration WebSocket frontend
- [SECURITY.md](SECURITY.md) - Guide de sécurité complet
- [.env.example](.env.example) - Template de configuration

---

## 🤝 Contribution

Les contributions sont les bienvenues ! Voici comment participer :

### 1. Fork le projet

```bash
git clone https://github.com/votre-username/osirion-core.git
cd osirion-core
```

### 2. Créer une branche

```bash
git checkout -b feature/ma-fonctionnalite
```

### 3. Commiter les changements

```bash
git commit -m "feat: Ajout de ma fonctionnalité"
```

### 4. Pousser et créer une PR

```bash
git push origin feature/ma-fonctionnalite
```

### Conventions de commit

Utiliser [Conventional Commits](https://www.conventionalcommits.org/) :

- `feat:` Nouvelle fonctionnalité
- `fix:` Correction de bug
- `docs:` Documentation
- `refactor:` Refactoring
- `perf:` Amélioration performances
- `test:` Tests
- `chore:` Tâches diverses

---

## 📝 Roadmap

### v1.0 (Actuel)
- ✅ Reconnaissance faciale temps réel
- ✅ Multi-caméras RTSP
- ✅ WebSocket streaming
- ✅ Reconnexion automatique

### v1.1 (En cours)
- 🔄 Authentification WebSocket JWT
- 🔄 Rate limiting
- 🔄 Tests unitaires

### v2.0 (Prévu)
- 📋 Architecture distribuée (workers GPU)
- 📋 Base de données Redis cache
- 📋 Metrics Prometheus/Grafana
- 📋 Dashboard admin React
- 📋 Support Kubernetes

---

## 📄 Licence

MIT License - voir [LICENSE](LICENSE) pour plus de détails.

---

## 👥 Auteurs

- **Équipe Osirion** - Développement initial

---

## 🙏 Remerciements

- [Ultralytics YOLO](https://github.com/ultralytics/ultralytics) - Détection faciale
- [InsightFace](https://github.com/deepinsight/insightface) - Reconnaissance faciale
- [ByteTrack](https://github.com/ifzhang/ByteTrack) - Tracking multi-objets
- [Flask-SocketIO](https://github.com/miguelgrinberg/Flask-SocketIO) - WebSocket

---

## 📞 Support

- **Issues** : [GitHub Issues](https://github.com/votre-org/osirion-core/issues)
- **Discussions** : [GitHub Discussions](https://github.com/votre-org/osirion-core/discussions)
- **Email** : support@osirion.com

---

<div align="center">

**⭐ Si ce projet vous aide, n'hésitez pas à lui donner une étoile ! ⭐**

Fait avec ❤️ par l'équipe Osirion

</div>

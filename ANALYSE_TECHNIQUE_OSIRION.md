# Analyse technique exhaustive — Projet **Osirion**
### Système intelligent de vidéosurveillance par IA (reconnaissance faciale + reconnaissance de plaques / LPR-ANPR)

> Document d'analyse pour le mémoire. Basé **uniquement** sur le code source réellement présent dans le dépôt.
> **Mise à jour** : les **deux modules** sont désormais implémentés et opérationnels — reconnaissance faciale (§5) **et** reconnaissance de plaques d'immatriculation (§6).
> Chaque affirmation incertaine est accompagnée d'un **niveau de confiance** : 🟢 Élevé (lu directement dans le code) · 🟡 Moyen (déduit) · 🔴 À vérifier par l'étudiant.

---

## Table des matières
1. [Présentation générale](#1-présentation-générale)
2. [Analyse fonctionnelle](#2-analyse-fonctionnelle)
3. [Architecture générale](#3-architecture-générale)
4. [Technologies utilisées](#4-technologies-utilisées)
5. [Module de reconnaissance faciale](#5-module-de-reconnaissance-faciale)
6. [Module de reconnaissance des plaques (LPR / ANPR)](#6-module-de-reconnaissance-des-plaques-lpr--anpr)
7. [Analyse de la base de données](#7-analyse-de-la-base-de-données)
8. [Diagrammes à produire pour le mémoire](#8-diagrammes-à-produire)
9. [Points faibles et limites](#9-points-faibles-et-limites)
10. [Pistes d'amélioration](#10-pistes-damélioration)

---

## 1. Présentation générale

### 1.1 Objectif principal
Osirion est une **plateforme de vidéosurveillance intelligente** qui exploite des flux vidéo RTSP de caméras IP pour **détecter, suivre et identifier automatiquement des personnes** (reconnaissance faciale) **et des véhicules** (reconnaissance de plaques d'immatriculation — LPR/ANPR), en **temps réel** et sur **plusieurs caméras simultanément**. Le système centralise les identités/véhicules connus, journalise les événements (avec capture d'image), lève des **alertes** sur les plaques surveillées (*blacklist*) et diffuse les flux annotés vers une interface web d'administration. 🟢

### 1.2 Contexte d'utilisation
Surveillance multi-caméras sur réseau local/IP (caméras RTSP). Le README du Core cite explicitement les cas d'usage : surveillance d'entreprise, contrôle d'accès intelligent, analyse de flux en magasin, sécurité événementielle, *smart cities*. 🟢

### 1.3 Problème résolu
- **Identification automatique** : reconnaître une personne enregistrée dès qu'elle apparaît devant n'importe quelle caméra, sans intervention humaine.
- **Suivi inter-caméras** : maintenir une identité unique (`person_id`) lorsqu'une personne se déplace d'une caméra à l'autre, tout en **réduisant massivement les appels au moteur de reconnaissance** (cache global → ~75-80 % d'appels API économisés d'après la documentation interne `MULTI_CAMERA_TRACKING.md`). 🟢 *(le chiffre de 75-80 % est une estimation du projet, non mesurée par un benchmark présent dans le code 🔴)*
- **Centralisation** : une base unique de personnes + un journal d'événements horodatés avec snapshots.

### 1.4 Utilisateurs cibles
Le backend définit **3 rôles** (`app/models/users.py`, `UserRole`) : 🟢
| Rôle | Droits (déduits du `auth_middleware.py`) |
|------|------------------------------------------|
| `admin` | Accès complet : gestion utilisateurs, caméras, personnes, monitoring système |
| `user`  | Gestion des caméras et ajout de personnes (pas la gestion des utilisateurs) |
| `viewer`| Lecture seule (consultation caméras, personnes, événements) |

Utilisateurs métier visés : opérateurs de sécurité / centres de supervision, administrateurs système. 🟡

---

## 2. Analyse fonctionnelle

### 2.1 Vue d'ensemble des fonctionnalités existantes

**Authentification & sécurité (backend)** 🟢
- Inscription, connexion, déconnexion (`/auth/register`, `/login`, `/logout`).
- JWT à deux niveaux : *access token* (30 min) + *refresh token* (7 j) avec **rotation** et stockage en base (`refresh_tokens`).
- Hachage des mots de passe (bcrypt via `auth_utils`), **verrouillage de compte** après échecs répétés (`failed_login_attempts`, `locked_until`).
- **Contrôle d'accès par rôle** (RoleChecker) + **rate limiting** (slowapi).
- Chiffrement des URL RTSP en base via **Fernet** (`security_utils.crypter/decrypter`).

**Gestion des personnes / enrôlement** 🟢
- Enrôlement par **1 image** (`POST /people/upload/`) avec augmentation automatique (flip, rotation ±7°, +15 % luminosité) → centroïde d'embeddings.
- Enrôlement par **2 à 5 images** (`POST /people/upload/multi/`) → centroïde direct.
- **Détection de doublons** au moment de l'enrôlement (refus si similarité cosinus > 0.90).
- Liste des personnes (`GET /people/list/`), recherche par embedding (`POST /people/search/`).

**Gestion des caméras** 🟢
- CRUD complet (`/cameras/add`, `/`, `/{id}`, `/update/{id}`, `/delete/{id}`), URL RTSP chiffrée.

**Journal d'événements** 🟢
- Création d'événement avec snapshot (`POST /events/add`), liste et consultation (`GET /events/`).
- Types d'événements définis : `RECOGNITION`, `ENTRY`, `EXIT`, `DETECTION` (constante `EVENTS` dans le Core). 🟢 *(Seul `RECOGNITION` est réellement émis par le pipeline actuel ; `ENTRY/EXIT/DETECTION` sont déclarés mais non générés 🟡)*

**Surveillance temps réel (core)** 🟢
- Capture RTSP multi-caméras (1 thread capture + 1 thread traitement par caméra) avec **reconnexion automatique** (backoff exponentiel, transport TCP forcé).
- Détection de visages + embeddings (InsightFace `buffalo_l`, GPU CUDA si dispo).
- **Tracking multi-objets** par ByteTrack (un tracker par caméra).
- **Filtre qualité de frame** (variance du Laplacien) pour rejeter les images floues avant l'inférence GPU.
- **Seuil de reconnaissance adaptatif par caméra** (méthode d'Otsu + lissage exponentiel).
- **Cache global inter-caméras** (`GlobalPersonTracker`) pour éviter les reconnaissances répétées.
- **Streaming WebSocket** (Flask-SocketIO) : diffusion des frames annotées (JPEG/base64) par « room » de caméra, avec cache JPEG partagé entre clients.
- API REST de service : `GET /api/cameras`, `GET /api/stats`.

**Reconnaissance de plaques d'immatriculation (LPR / ANPR)** 🟢
- Détection de plaque (**YOLO** Ultralytics) + lecture des caractères (**EasyOCR**) sur les flux du Core, **en parallèle** du pipeline facial et **sans le perturber**.
- Registre des véhicules connus / surveillés (CRUD table `Vehicle` : plaque, propriétaire, notes, *blacklist*).
- **Recherche floue** d'une plaque lue (tolérante aux confusions OCR O↔0, I↔1…) via `POST /plates/search`.
- **Alerte blacklist** : log d'alerte dédié quand une plaque surveillée est détectée + annotation rouge dans le flux.
- Événement `PLATE_RECOGNITION` horodaté avec snapshot, texte de plaque et lien vers le véhicule connu.
- **Activation à chaud** (opt-in) via l'API du Core (`/api/lpr/toggle`) pilotée par l'interrupteur du frontend, **sans redémarrage**.

**Interface web (frontend Next.js)** 🟢
- Dashboard admin : visualisation **live** (canvas + socket.io, badge « LPR actif »), gestion caméras, gestion utilisateurs, **gestion des plaques** (page *Plaques* + outil de test de la recherche floue), état système, paramètres, pages *blacklist* et *alerts*.
- Proxy d'API côté serveur Next.js vers le backend, `AuthContext`, `RoleGuard`, rafraîchissement de token (`fetchWithRefresh.js`).

**Monitoring système** 🟢
- `GET /sysInfo/` (admin) : CPU, RAM, swap, disques, réseau via `psutil`.
- Endpoints de santé : backend `/health` (DB + état index FAISS), core `/api/stats`.

### 2.2 Fonctionnalités **terminées** (opérationnelles dans le code) 🟢
- Authentification JWT complète + rôles + rate limiting + verrouillage compte.
- Enrôlement facial (mono- et multi-images) avec centroïde et anti-doublon.
- Index vectoriel FAISS (cosinus) + recherche par similarité.
- Pipeline live : capture RTSP → détection/embedding → ByteTrack → reconnaissance → événement → streaming WebSocket.
- Cache global inter-caméras thread-safe.
- **Module de reconnaissance de plaques (LPR/ANPR)** complet : détection YOLO + OCR EasyOCR + tracking dédié + vote temporel + recherche floue + alerte blacklist + événement `PLATE_RECOGNITION`, activable à chaud (cf. §6).
- Frontend de supervision (live, caméras, utilisateurs, **plaques**, settings, system-status).
- Orchestration Docker Compose des 4 services (db, backend, core, frontend) avec support GPU NVIDIA.

### 2.3 Fonctionnalités **en cours / partielles** 🟡
- **Événements ENTRY/EXIT/DETECTION** : types déclarés mais seul `RECOGNITION` est émis. 🟢
- **Pages frontend `blacklist` et `alerts`** : présentes dans l'arborescence ; côté **plaques**, la *blacklist* est désormais réelle (champ `Vehicle.is_blacklisted` + endpoint `/plates/blacklist/{id}` + alerte au log). En revanche une *blacklist*/`alerts` **faciale** (par personne) n'a toujours pas de table/endpoint dédié. 🟡
- **Vérification d'email / `is_verified`** : champ présent, mais l'envoi d'email est marqué `TODO` dans `auth_routes.py`.
- **Réinitialisation de mot de passe** : endpoint présent mais corps `TODO` (pas d'envoi d'email).
- **Authentification du WebSocket du Core** : signalée « TODO » dans le README (le flux vidéo n'est pas protégé par JWT côté Socket.IO). 🟢
- Présence de **deux points d'entrée Core** (`main.py` legacy monolithique et `main_refactored.py` modulaire) et de **deux modules de détection** (`face_detection.py`, `face_detection_new.py`) → dette technique / code en transition. 🟢

### 2.4 Fonctionnalités **prévues mais NON implémentées** 🟢
- **Détection d'objets** : simple *toggle* UI (`settings.objectDetection`), non implémenté.
- ✅ *(Désormais implémenté)* La **reconnaissance des plaques** n'est plus un placeholder : l'interrupteur `settings.licencePlateRecognition` est maintenant **câblé** sur un module LPR/ANPR complet (backend + core + frontend + table). Voir §6.
- Roadmap README (non implémentée) : architecture distribuée (workers GPU), cache Redis, métriques Prometheus/Grafana, support Kubernetes, API REST enrichie de trajectoires (`/api/persons/{id}/trajectory`, etc.).

---

## 3. Architecture générale

### 3.1 Vue macroscopique : 4 services conteneurisés
Le `docker-compose.yml` racine orchestre **4 services** sur un réseau bridge `osirion` : 🟢

```
┌──────────────┐   HTTP/REST    ┌───────────────────┐   SQL (psycopg2)   ┌──────────────────────┐
│  FRONTEND    │ ─────────────▶ │     BACKEND        │ ─────────────────▶ │   POSTGRESQL 15      │
│  Next.js 15  │  (proxy SSR)   │  FastAPI :8000     │                    │   + pgvector         │
│  :3000       │ ◀───────────── │  (auth, people,    │ ◀───────────────── │  (camera, people,    │
└──────┬───────┘                │   cameras, events) │                    │   user, event,       │
       │                        └─────────▲──────────┘                    │   refresh_tokens)    │
       │ WebSocket (socket.io)            │ REST (JWT)                     └──────────────────────┘
       │ navigateur ──────────┐           │ /people/search, /events/add
       ▼                      ▼           │
┌─────────────────────────────────────────┴─────────┐        RTSP        ┌──────────────────┐
│                   CORE  (Flask :5000)               │ ◀───────────────── │  Caméras IP      │
│  SurveillanceSystem · CameraCapture · ByteTrack     │                    │  (flux RTSP)     │
│  InsightFace(GPU) · GlobalPersonTracker · WebStream │                    └──────────────────┘
└─────────────────────────────────────────────────────┘
```

| Service | Image / techno | Port | Rôle |
|---------|----------------|------|------|
| `db` | `pgvector/pgvector:pg15` | 5432 (interne) | Stockage relationnel + vecteurs 512D |
| `backend` | FastAPI (image `osirion-backend:gpu`) | 8000 | API métier, enrôlement, recherche FAISS, auth |
| `core` | Flask + Flask-SocketIO (`osirion-core:gpu`) | 5000 | Traitement vidéo temps réel + streaming |
| `frontend` | Next.js standalone | 3000 | Interface d'administration |

> Les services `backend` et `core` réservent un **GPU NVIDIA** (`deploy.resources.reservations.devices`). 🟢

### 3.2 Composants principaux

**Backend (FastAPI)** — `Osirion-backend-main/app/`
- `main.py` : montage des routers, CORS, fichiers statiques (`/uploads`, `/cropped`, `/snapshots`), construction de l'index FAISS au démarrage, `/health`.
- `routes/` : `auth_routes`, `people_routes`, `cameras_routes`, `events_routes`, `users_routes`, `monitoring_routes`, **`plates_routes`** (CRUD véhicules + recherche floue LPR).
- `services/` : `embeddings_service` (InsightFace + enrôlement/centroïde), `Faiss_search_service` (index + recherche cosinus), `detection_service` (YOLOv11n-face — *legacy*), `saveImage_service`, `bytesToImage_service`, `sys_monitoring_service`, `recognition_service` (**fichier quasi vide** 🟢).
- `models/` : `users`, `people`, `cameras`, `events` (étendu LPR), **`vehicles`** (table `Vehicle`).
- `schemas/` : `events_schema`, **`vehicles_schema`** (Vehicle CRUD + PlateSearch).
- `middleware/` : `auth_middleware` (JWT + rôles), `rate_limit` (slowapi).
- `utils/` : `auth_utils` (JWT, bcrypt, lockout), `security_utils` (Fernet), `images_utils`, **`plate_utils`** (normalisation + similarité floue Levenshtein/repliement OCR).
- `alembic/` : 3 migrations (création initiale ; colonnes user/refresh_tokens ; **table `vehicle` + colonnes plaque sur `event`**).

**Core (surveillance temps réel)** — `Osirion-core-master/`
- `main_refactored.py` : point d'entrée (logging, signaux, lancement `SurveillanceSystem`, activation du streaming).
- `core/surveillance_system.py` : orchestrateur (init caméras, structures, threads, tracker global).
- `core/camera_manager.py` (`CameraCapture`) : capture RTSP + reconnexion backoff.
- `core/tracking_processor.py` (`TrackingProcessor`) : pipeline détection→tracking→reconnaissance→annotation.
- `core/global_person_tracker.py` (`GlobalPersonTracker`) : cache identités inter-caméras (cosinus vectorisé, thread-safe).
- `core/adaptive_threshold.py` (`AdaptiveThreshold`) : seuil par caméra (Otsu + EWM).
- `core/web_streaming.py` (`WebStreamingServer`) : Flask-SocketIO, broadcast frames + **routes REST `/api/lpr/status` et `/api/lpr/toggle`** (état/activation à chaud du LPR).
- `core/runtime_control.py` (`RuntimeControl`) : drapeau LPR thread-safe, modifiable à chaud par le frontend sans redémarrer le Core.
- `core/plate_processor.py` (`PlateProcessor`) : pipeline LPR **par caméra** (détection → tracking dédié → OCR avec frame-skipping → vote temporel → worker réseau découplé → annotation).
- `face_detection.py` : InsightFace `buffalo_l` (détection SCRFD + embedding ArcFace 512D, GPU).
- `plate_detection.py` : singletons **YOLO** (détection plaque) + **EasyOCR** (lecture), `LPR_AVAILABLE`, dégradation gracieuse, pré-traitement OCR (CLAHE, anti-reflet, deskew).
- `services/` : `embeddings_search_service` (POST /people/search async), `event_services` (`send_event_async` facial + **`send_plate_event_async`** LPR), `camera_fetching_service` (GET /cameras), **`plate_search_service`** (POST /plates/search async).
- `utils/auth_utils.py` : login machine-to-machine (le Core s'authentifie au backend avec un compte de service).
- `ByteTrack/` (cloné dans l'image) + `patches/` (correctifs NumPy ≥ 1.24).
- Modèles embarqués dans l'image : `yolov11n-face.pt`, **`license_plate_detector.pt`** + poids EasyOCR pré-téléchargés au build.

**Frontend (Next.js 15, App Router)** — `Osirion-front-end-main/app/`
- `Osirion/admin/` : `live/` (+`CameraStream.js` socket.io, badge LPR), `cameras/`, `users/`, **`plates/`** (gestion des véhicules + test de recherche floue), `blacklist/`, `alerts/`, `system-status/`, `settings/` (interrupteur LPR câblé sur le Core), plus `AdminSidebar` (entrée *Plaques*), `AdminTopBar`, `AuthContext`, `RoleGuard`.
- `api/` : routes proxy (login, users, events, images, people, cameras, **plates** + `plates/search` + `plates/[id]/blacklist`, auth/me, auth/refresh, systemHealth).
- `lib/fetchWithRefresh.js` : appels authentifiés avec refresh automatique.

### 3.3 Interactions entre composants & flux de données

**A. Enrôlement d'une personne (frontend → backend → DB/FAISS)** 🟢
1. L'admin envoie une ou plusieurs images via le frontend.
2. `people_routes.upload[/multi]` → `embeddings_service.enroll_from_images` : détection SCRFD + embedding ArcFace → **centroïde 512D** L2-normalisé.
3. Anti-doublon via `search_similar_people` (rejet si cosinus > 0.90).
4. Sauvegarde image originale (`uploads/`) + crop (`cropped/`), insertion `People` (embedding en colonne `pgvector`), ajout au vecteur FAISS (`add_person_to_index`).

**B. Reconnaissance live (caméra → core → backend → DB)** 🟢
1. `CameraCapture` lit le flux RTSP, redimensionne en 640×480, pousse dans une `queue` (maxsize 4).
2. `TrackingProcessor` traite 1 frame sur `PROCESS_EVERY_N_FRAME` (3 en GPU) :
   - **Filtre flou** (Laplacien < seuil → frame réutilise les dernières annotations).
   - `detect_faces_with_embeddings` (un seul passage GPU : détection + alignement + embedding).
   - `ByteTracker.update` → tracks persistants avec `track_id`.
   - Pour chaque track nouveau ou à ré-identifier : recherche dans le **cache global** ; sinon `POST /people/search` (FAISS cosinus) sur le backend.
   - Si score > seuil adaptatif → personne reconnue → `find_or_register` (cache global) + `POST /events/add` (snapshot + `person_id` + score).
   - Annotation des bounding boxes (vert reconnu / rouge inconnu).
3. La frame annotée est stockée (`result_frames[cam_id]`) et diffusée par `WebStreamingServer` aux clients abonnés.

**C. Visualisation (navigateur ↔ core)** 🟢
- Le navigateur ouvre une connexion Socket.IO vers le Core (`:5000`), émet `start_stream {camera_id}`, reçoit l'événement `frame` (JPEG base64) à ~30 FPS, et dessine sur un `<canvas>`.

**D. Authentification machine (core → backend)** 🟢
- `utils/auth_utils.py` du Core se connecte avec un compte de service (`AUTH_EMAIL`/`AUTH_PASSWORD`), conserve l'access/refresh token, et le rafraîchit (re-check `/auth/me` au plus 1×/min).

**E. Reconnaissance de plaque live (caméra → core → backend → DB)** 🟢 *(si LPR activé)*
1. Sur une frame **déjà traitée** par le pipeline facial, `TrackingProcessor._run_plate_detection` appelle `PlateProcessor.process` (chargement paresseux du module à la 1re activation).
2. `detect_plates` (**YOLO**, 1 frame sur `PLATE_PROCESS_EVERY_N`) → boîtes de plaques → **ByteTracker dédié** (track_id persistants).
3. Pour chaque track non « définitif » : gating taille/netteté → crop → pré-traitement → `read_plate_text` (**EasyOCR**) → **vote temporel** caractère par caractère le long du track.
4. Plaque finalisée → mise en **file FIFO** ; un **thread worker** (asyncio + aiohttp dédiés) exécute `POST /plates/search` (recherche floue) puis, si besoin, `POST /events/add` (`PLATE_RECOGNITION`, snapshot + `plate_text_detected` + `vehicle_id`). **Le thread caméra n'est jamais bloqué par le réseau.**
5. Si la plaque correspond à un véhicule **blacklisté** → log d'**ALERTE** dédié ; annotation rouge dans le flux (jaune = lue, bleu = connue).

---

## 4. Technologies utilisées

### 4.1 Langages
- **Python 3.12** (backend + core). 🟢
- **JavaScript / JSX** (frontend, React 19). 🟢
- **SQL** (PostgreSQL). **Dockerfile / YAML** (déploiement).

### 4.2 Frameworks & bibliothèques
| Domaine | Backend | Core | Frontend |
|---------|---------|------|----------|
| Web/API | **FastAPI**, Uvicorn, SQLModel, Pydantic, slowapi | **Flask**, **Flask-SocketIO**, python-socketio, aiohttp, requests | **Next.js 15**, React 19, Tailwind CSS, lucide-react, socket.io-client |
| IA / Vision | **InsightFace** (`buffalo_l`), ONNX Runtime, OpenCV, NumPy, **Ultralytics YOLO**, **rapidfuzz** (matching plaques) | InsightFace (GPU), ONNX Runtime GPU, OpenCV (headless), **ByteTrack**, lapx, scipy, filterpy, **Ultralytics YOLO** (plaques), **EasyOCR** + torch | — |
| Recherche | **FAISS** (visages, cosinus), **Levenshtein/rapidfuzz** (plaques, fuzzy) | — | — |
| Base de données | **pgvector** (SQLAlchemy), psycopg2, Alembic | — | — |
| Sécurité | PyJWT, **bcrypt** (passlib), **cryptography/Fernet** | PyJWT | JWT côté cookies/headers |
| Système | psutil | psutil, rich, loguru | — |

### 4.3 Bibliothèques IA — détail 🟢
- **InsightFace `buffalo_l`** = détecteur **SCRFD** + extracteur **ArcFace** (embedding **512 dimensions**). Utilisé **à la fois** dans le Core (live, GPU) et le Backend (enrôlement, CPU).
- **ByteTrack** (YOLOX tracker) pour le suivi multi-objets (association IoU + Kalman).
- **YOLOv11n-face** (`yolov11n-face.pt`, Ultralytics) : présent dans `detection_service.py` du backend mais **non utilisé par le pipeline actuel** (l'enrôlement passe par InsightFace). 🟡 Le README du Core mentionne YOLOv11n pour la détection, mais le code effectif (`face_detection.py`) utilise SCRFD d'InsightFace → **incohérence doc/code à signaler**. 🟢
- **FAISS** : `IndexFlatIP` (produit scalaire = cosinus sur vecteurs normalisés) si < 1000 vecteurs ; bascule vers `IndexIVFFlat` (< 1 M) puis `IndexIVFPQ` (≥ 1 M).
- **YOLO de plaque** (`license_plate_detector.pt`, Ultralytics) : détecteur d'objet « plaque » exécuté sur les frames du Core, **FP16** sur GPU (fallback FP32 auto). Distinct du `yolov11n-face.pt` (legacy) et de SCRFD.
- **EasyOCR** (détecteur de texte **CRAFT** + recognizer CRNN) : lecture des caractères de la plaque ; langue `en`, `allowlist` alphanumérique ; modèles pré-téléchargés au build (~100 Mo). 🟢
- **rapidfuzz** (distance de Levenshtein, optionnel) : matching flou des plaques côté backend ; **fallback pur-Python** intégré si absent → la recherche fonctionne toujours. 🟢

### 4.4 Base de données
- **PostgreSQL 15** + extension **pgvector** (colonne `Vector(512)` pour les embeddings). 🟢
- Migrations gérées par **Alembic**.

### 4.5 Outils de déploiement
- **Docker** + **Docker Compose** (4 services), images CPU/GPU séparées (`requirements-cpu.txt` / `requirements-gpu.txt`).
- **nvidia-container-toolkit** requis pour le GPU.
- `build_images.py` (script de build), bind-mounts pour hot-reload du code.
- Healthchecks Docker sur chaque service.

### 4.6 Autres dépendances notables
- **slowapi** (rate limiting), **python-dotenv** (config `.env`), **loguru/rich** (logs Core), **psutil** (monitoring).

---

## 5. Module de reconnaissance faciale

> **Confiance globale : 🟢 Élevée** — lu intégralement dans `face_detection.py`, `tracking_processor.py`, `embeddings_service.py`, `Faiss_search_service.py`, `global_person_tracker.py`, `adaptive_threshold.py`.

### 5.1 Modèles & algorithmes
| Étape | Algorithme / modèle | Détail |
|-------|---------------------|--------|
| Détection de visage | **SCRFD** (InsightFace `buffalo_l`) | `det_size=(640,640)`, seuil de confiance 0.7 (live) / 0.85 (enrôlement) |
| Alignement | 5 points (interne InsightFace) | aligne avant l'extraction ArcFace |
| Embedding | **ArcFace** | vecteur **512D**, **L2-normalisé** (norme=1.0) |
| Suivi | **ByteTrack** | `track_thresh=0.5`, `match_thresh=0.8`, `track_buffer≈10` frames |
| Comparaison | **Similarité cosinus** | via FAISS `IndexFlatIP` (back) et numpy vectorisé (cache global) |
| Seuil | **Adaptatif (Otsu + EWM)** | initial 0.45, plancher 0.35, plafond 0.80 |
| Qualité image | **Variance du Laplacien** | seuil 80 (640×480 RTSP) ; rejette les frames floues |

### 5.2 Pipeline complet — Enrôlement (offline)
```
Image(s) ──▶ [Filtre flou (Laplacien ≥ 60)] ──▶ [SCRFD détection (det_score ≥ 0.85)]
        │                                              │
        │ (si 1 seule image)                           ▼
        └─▶ 4 augmentations (flip, ±7°, +15% lum.)   [ArcFace embedding 512D + L2-norm]
                                                       │
                                          [Centroïde = moyenne des embeddings → re-L2-norm]
                                                       │
                              [Anti-doublon : cosinus > 0.90 ? → refus]
                                                       │
        [Insertion People (pgvector) + image uploads/ + crop cropped/ + FAISS add_person_to_index]
```

### 5.3 Pipeline complet — Reconnaissance (temps réel)
```
RTSP ─▶ CameraCapture ─(queue)─▶ TrackingProcessor (1 frame / N)
                                    │
                          [Quality gate : Laplacien < 80 ? → skip GPU, réutilise annotations]
                                    │ sinon
                          [SCRFD + ArcFace (1 passe GPU) → faces (bbox, conf, embedding 512D)]
                                    │
                          [ByteTrack.update → tracks (track_id persistants)]
                                    │
                  pour chaque track nouveau / à ré-identifier (intervalle 200 frames) :
                                    │
                    ┌───────────────┴────────────────┐
                    ▼                                 ▼
        [Cache global ? cosinus ≥ 0.50]      sinon  [POST /people/search (FAISS cosinus)]
            │ HIT (≈5 ms)                              │
            ▼                                          ▼
   update_person_location                  [score > seuil adaptatif ?]
                                                       │ oui
                                          [find_or_register (person_id unique)]
                                                       │
                                          [POST /events/add (snapshot + score)]
                                    │
                          [Annotation bbox + label (vert/rouge) → result_frames]
                                    │
                          [WebStreamingServer → Socket.IO 'frame' → navigateur]
```

### 5.4 Points d'ingénierie remarquables (à valoriser dans le mémoire) 🟢
- **Cohérence d'échelle cosinus** entre FAISS et cache global (les deux sur `[0,1]`, plus de scaling `(cos+1)/2`).
- **Seuil adaptatif par caméra** : Otsu sépare la distribution bimodale (matches vs non-matches), avec lissage exponentiel et garde-fous plancher/plafond.
- **Cache global thread-safe** avec opération `find_or_register` **atomique** (évite les doublons quand 2 caméras reconnaissent simultanément).
- **Optimisation réseau** : session aiohttp persistante, recherches en parallèle (`asyncio.gather`), retry + backoff, cache JPEG partagé entre clients du streaming.
- **Filtre de netteté** avant inférence GPU (≈0,3 ms vs 15-30 ms d'inférence économisée sur frame floue).

---

## 6. Module de reconnaissance des plaques (LPR / ANPR)

> **Statut : ✅ IMPLÉMENTÉ ET OPÉRATIONNEL.**
> **Confiance globale : 🟢 Élevée** — lu intégralement dans `plate_detection.py`, `core/plate_processor.py`, `core/tracking_processor.py` (intégration), `core/runtime_control.py`, `core/web_streaming.py`, `services/plate_search_service.py`, `services/event_services.py`, `app/routes/plates_routes.py`, `app/utils/plate_utils.py`, `app/models/vehicles.py`, `app/schemas/vehicles_schema.py`, migration `c3d4e5f6a7b8`, et le frontend (`plates/`, `settings/`, `CameraStream.js`).

### 6.1 Principe : un pipeline **symétrique** au module facial
Le module plaques réutilise l'architecture du module facial, en remplaçant chaque brique « visage » par son équivalent « plaque » :

| Étape | Module facial (§5) | Module plaques (LPR) |
|-------|--------------------|----------------------|
| Détection | SCRFD (InsightFace) | **YOLO** (Ultralytics, `license_plate_detector.pt`) |
| Extraction | ArcFace → embedding 512D | **EasyOCR** → texte de la plaque |
| Suivi | ByteTrack (1 tracker/caméra) | **ByteTrack dédié** (1 tracker plaques/caméra, en parallèle) |
| Référentiel connu | table `People` | table **`Vehicle`** |
| Recherche | cosinus (FAISS) | **similarité floue** (Levenshtein + repliement OCR) |
| Événement | `RECOGNITION` | **`PLATE_RECOGNITION`** |

Le pipeline LPR s'exécute **dans le même thread de traitement** que le facial (`TrackingProcessor`), sur la **même frame**, **après** le traitement facial — sans jamais le perturber.

### 6.2 Principe directeur : opt-in & **dégradation gracieuse** 🟢
Choix d'ingénierie central : *le module plaques ne doit JAMAIS casser le pipeline facial existant.*
- **Opt-in** : `ENABLE_PLATE_RECOGNITION` vaut `false` par défaut. Activation **à chaud** via l'API du Core (`POST /api/lpr/toggle` → `RuntimeControl`, thread-safe), branchée sur l'interrupteur du frontend (page *Paramètres*) — **sans redémarrer** le Core. Le drapeau runtime est prioritaire sur la config.
- **Dégradation gracieuse** : si `ultralytics`/`easyocr` sont absents, ou si les poids YOLO sont introuvables, `plate_detection.py` se charge **quand même** mais expose `LPR_AVAILABLE = False` et `detect_plates()` renvoie `[]`. Le facial continue, inchangé.
- **Chargement paresseux** : le `PlateProcessor` d'une caméra n'est instancié qu'à la **1re activation** (`_ensure_plate_processor`) ; une init en échec est mémorisée (`_lpr_init_failed`) pour ne pas boucler.

### 6.3 Modèles & algorithmes 🟢
| Étape | Algo / modèle | Détail |
|-------|---------------|--------|
| Détection plaque | **YOLO** (Ultralytics) | `license_plate_detector.pt`, conf ≥ 0.45, **FP16** sur GPU (fallback FP32 auto) |
| Suivi | **ByteTrack** | tracker dédié plaques, 1 par caméra (indépendant du tracker visages) |
| Pré-traitement OCR | OpenCV | upscale des petits crops, **CLAHE**, robustesse éclairage (anti-reflet par *inpainting*, gamma adaptatif, normalisation d'illumination — **conditionnels**), *deskew* optionnel |
| OCR | **EasyOCR** (CRAFT + recognizer) | langue `en`, `allowlist` A-Z/0-9, tri des fragments par bande verticale puis gauche→droite (gère les plaques **2 lignes**) |
| Normalisation | regex | majuscules + suppression des non-alphanumériques (`"1-abc 234"` → `"1ABC234"`) |
| Longueur | bornes | plaque retenue si **4 ≤ longueur ≤ 10** caractères |
| Recherche | **Levenshtein normalisée** + repliement OCR | tolère O↔0, I↔1, S↔5, B↔8, Z↔2, G↔6 ; seuil 0.82 |

### 6.4 Optimisations latence & précision 🟢 (à valoriser dans le mémoire)
- **Résolution réseau DÉCOUPLÉE** : la recherche floue + l'envoi d'événement partent dans un **thread worker dédié** (file FIFO + boucle asyncio + session aiohttp propres). Le thread caméra ne fait que détecter/lire/annoter et **n'est jamais bloqué** par la latence backend (avant ce découplage, un backend lent pouvait figer le flux plusieurs secondes).
- **Cadence de détection** : YOLO ne tourne qu'**1 frame traitée sur `PLATE_PROCESS_EVERY_N`** (défaut 2) ; le cache par `track_id` redessine les boîtes sur les frames intermédiaires (`annotate_cached`) sans réinférence.
- **Frame-skipping OCR** : une fois la plaque « définitive » pour un track, l'OCR est **complètement sauté** pour ce track.
- **Vote temporel** : au lieu de figer la 1re lecture haute-confiance, on **accumule** les lectures le long du track et on **vote caractère par caractère**, pondéré par la confiance — d'abord la longueur la plus représentée, puis, à chaque position, le caractère au score de confiance cumulé maximal. Finalisation quand le consensus est vu ≥ `PLATE_VOTE_MIN_AGREE` (2) fois avec confiance moyenne ≥ 0.65 (`ocr_good`), **ou** après `PLATE_OCR_MAX_ATTEMPTS` (5) tentatives. Robuste aux flous/reflets ponctuels.
- **Gating** : pas d'OCR sur les crops trop petits (< 60×18 px) ou (option) trop flous (variance du Laplacien) → moins de calcul, moins de lectures parasites.
- **Validation de format (regex optionnelle)** : une plaque hors-format n'est jamais recherchée → moins de faux positifs *blacklist*.
- **Singletons + verrous** : YOLO et EasyOCR chargés **une seule fois**, partagés entre caméras/threads ; inférences protégées par verrous (concurrence CUDA/torch). **Warm-up** au démarrage (1re inférence à blanc) pour éviter le pic de latence sur la 1re vraie plaque.
- **Modèles embarqués dans l'image Docker** : `license_plate_detector.pt` copié + poids EasyOCR (CRAFT + 'en', ~100 Mo) **pré-téléchargés au build** → aucun téléchargement au runtime.

### 6.5 Pipeline complet — LPR temps réel
```
RTSP ─▶ frame déjà traitée (TrackingProcessor) ──(si LPR activé)──▶ PlateProcessor.process()
                                                                    │
                            [cadence : 1 frame YOLO sur N]          │
                                                                    ▼
                          [YOLO detect_plates → bboxes plaques (conf ≥ 0.45)]
                                                                    │
                          [ByteTrack plaques → track_id persistants]
                                                                    │
                  pour chaque track non « définitif » :             │
                          [gating taille/netteté] ─▶ [crop] ─▶ [pré-traitement OCR]
                                                                    │
                          [EasyOCR read_plate_text → (texte normalisé, conf)]
                                                                    │
                          [vote temporel caractère/caractère → consensus]
                                                                    │
                          [finalisé ?] ──oui──▶ file FIFO ─▶ WORKER RÉSEAU (thread dédié) :
                                                          [POST /plates/search (fuzzy, seuil 0.82)]
                                                          [si match blacklisté → 🚨 ALERTE (log)]
                                                          [POST /events/add (PLATE_RECOGNITION,
                                                              snapshot + plate_text + vehicle_id)]
                                                                    │
                          [annotation bbox+label : jaune=lue / bleu=connue / rouge=BLACKLIST]
                                                                    │
                          [WebStreamingServer → Socket.IO → navigateur (badge « LPR actif »)]
```

### 6.6 Modèle de données & API 🟢
- **Table `Vehicle`** (cf. §7.1) : `plate_text` (normalisé, **unique, indexé**), `owner_name`, `is_blacklisted` (indexé), `notes`. C'est l'équivalent « véhicule » de `People`.
- **`event`** étendu : `plate_text_detected` + `vehicle_id` (FK → `vehicle`, **`ON DELETE SET NULL`**) ; `event_type = "PLATE_RECOGNITION"`.
- **Endpoints `/plates`** (montés dans `app/main.py`) : `add`, `/` (liste, filtre `blacklisted_only`), `/{id}`, `update/{id}`, `blacklist/{id}`, `delete/{id}`, **`search`** (fuzzy, *rate-limité* 600/min). Permissions réutilisant les `RoleChecker` existants : lecture/recherche = `viewer`+, écriture = `user`+.
- **Recherche floue** (`/plates/search`) : normalisation → tentative **exacte** (score 1.0) → sinon similarité de Levenshtein, prise comme **max** entre la chaîne brute et la chaîne **OCR-repliée** ; on garde les `k` meilleures ≥ `threshold`. `rapidfuzz` **optionnel** (fallback pur-Python). Côté Core, `plate_search_service` gère le refresh-token sur 401 + backoff sur 429/5xx.

### 6.7 Intégration frontend 🟢
- **Page *Plaques*** (`admin/plates/page.js`) + entrée de menu *Plaques* : liste filtrable (tous / blacklist / connues), recherche, ajout/édition (plaque, propriétaire, notes, bascule blacklist), suppression, bascule blacklist directe, **et un outil de test** de la recherche floue (saisir une plaque → `/plates/search`).
- **Page *Paramètres*** : l'interrupteur « Plaques d'immatriculation » — auparavant un simple placeholder UI — est désormais **câblé** sur l'état réel du Core (`/api/lpr/status` au montage, `/api/lpr/toggle` au clic) et affiche `lpr_available`.
- **Vue *Live*** (`CameraStream.js`) : poll de `/api/lpr/status` (~15 s) → **badge « LPR actif »** + légende des couleurs ; les boîtes plaques sont **incrustées dans le flux par le Core** (aucune logique de dessin côté navigateur).

### 6.8 Configuration 🟢
~30 paramètres pilotables par variables d'environnement (`config/settings.py`, bloc *Module LPR/ANPR*) : `ENABLE_PLATE_RECOGNITION`, chemin du modèle, seuils détection/OCR, langues, allowlist, longueurs min/max, seuil de recherche, TTL du cache (600 frames), couleurs d'annotation, et les paramètres d'optimisation (cadence, taille de file, gating taille/netteté, vote temporel, pré-traitement, robustesse éclairage, FP16, regex de format).

### 6.9 Limites / points de vigilance du module (🟢/🟡)
- L'**événement plaque** stocke le **snapshot de la frame entière**, pas le crop de la plaque seul (pas de colonne « image de plaque » dédiée). 🟢
- La précision OCR dépend fortement des **conditions réelles** (résolution, angle, éclairage, mouvement) ; aucun **benchmark chiffré** n'est présent dans le dépôt → à mesurer par l'étudiant sur son jeu de tests. 🔴
- L'OCR est configuré pour la **langue `en`** et un *allowlist* alphanumérique générique — à adapter au **format local** des plaques visées (un `PLATE_FORMAT_REGEX` est prévu pour ça). 🟡
- Pas d'**alerte temps réel poussée** au frontend sur détection blacklist : l'alerte existe en **log** côté Core (et l'événement est journalisé), mais pas (encore) de notification WebSocket dédiée vers l'opérateur. 🟢

---

## 7. Analyse de la base de données

> Source : `app/models/*.py` + migrations Alembic. 🟢

### 7.1 Tables et entités

**`camera`** — caméras de surveillance
| Colonne | Type | Rôle |
|---------|------|------|
| `id` | int (PK) | identifiant |
| `cam_name` | varchar(50) | nom |
| `rtsp_url` | text | **URL RTSP chiffrée (Fernet)** |
| `location` | varchar(100) | emplacement |
| `is_active` | bool | caméra active ou non (filtrée par le Core) |
| `created_at` | datetime | date de création |

**`people`** — personnes connues / enrôlées
| Colonne | Type | Rôle |
|---------|------|------|
| `id` | int (PK) | identifiant |
| `first_name`, `last_name` | varchar(50) | identité |
| `phone` | varchar(20) **unique** | téléphone |
| `email` | varchar(100) **unique** | email |
| `addresse` | varchar(100) | adresse |
| `image_url` | text | chemin image originale |
| `embeddings` | **`Vector(512)`** (pgvector) | empreinte faciale (centroïde ArcFace) |
| `created_at` | datetime | date d'enrôlement |

**`user`** — comptes d'accès à la plateforme
| Colonne | Type | Rôle |
|---------|------|------|
| `id` | int (PK) | identifiant |
| `fullName` | varchar(80) | nom complet |
| `email` | varchar(100) **unique, indexé** | login |
| `usr_password` | text | **mot de passe haché (bcrypt)** |
| `role` | varchar(20) | `admin` / `user` / `viewer` |
| `is_active`, `is_verified` | bool | statut du compte |
| `created_at`, `updated_at`, `last_login` | datetime | horodatages |
| `failed_login_attempts` | int | anti-bruteforce |
| `locked_until` | datetime | verrouillage temporaire |

**`refresh_tokens`** — jetons de rafraîchissement JWT
| Colonne | Type | Rôle |
|---------|------|------|
| `id` | int (PK) | identifiant |
| `user_id` | int (FK → user.id, indexé) | propriétaire |
| `token` | text **unique, indexé** | valeur du refresh token |
| `expires_at` | datetime | expiration |
| `created_at` | datetime | création |
| `is_revoked` | bool | révocation (rotation/logout) |
| `device_info` | varchar(255) | User-Agent |
| `ip_address` | varchar(45) | IP du client |

**`event`** — journal des événements détectés *(étendu pour le LPR)*
| Colonne | Type | Rôle |
|---------|------|------|
| `id` | int (PK) | identifiant |
| `camera_id` | int (FK → camera.id) | caméra source |
| `person_id` | int (FK → people.id, nullable) | personne reconnue (ou null) |
| `event_type` | varchar(30) | `RECOGNITION` · **`PLATE_RECOGNITION`** (et prévus ENTRY/EXIT/DETECTION) |
| `confidence` | float (nullable) | score (reconnaissance faciale **ou** confiance OCR) |
| `snapshot_url` | text (nullable) | image capturée (`snapshots/`) |
| `plate_text_detected` | varchar(20) **(nullable)** | **texte de plaque lu (normalisé)** — renseigné si `PLATE_RECOGNITION` |
| `vehicle_id` | int (FK → vehicle.id, **nullable, ON DELETE SET NULL**) | **véhicule connu correspondant (null si plaque inconnue)** |
| `timestamp` | datetime | horodatage |

**`vehicle`** — véhicules connus / surveillés *(registre des plaques — équivalent « véhicule » de `people`)* 🟢
| Colonne | Type | Rôle |
|---------|------|------|
| `id` | int (PK) | identifiant |
| `plate_text` | varchar(20) **unique, indexé** | **plaque NORMALISÉE** (majuscules, alphanumérique) |
| `owner_name` | varchar(100) (nullable) | propriétaire déclaré |
| `is_blacklisted` | bool **(indexé)** | véhicule sous surveillance → déclenche une **alerte** |
| `notes` | varchar(255) (nullable) | métadonnées d'exploitation |
| `created_at` | datetime | date d'enregistrement |
| `updated_at` | datetime (nullable) | dernière modification |

### 7.2 Relations
- `event.camera_id` → **`camera.id`** (N:1) — chaque événement provient d'une caméra. 🟢
- `event.person_id` → **`people.id`** (N:1, optionnel) — un événement peut concerner une personne connue ou non (null). 🟢
- `event.vehicle_id` → **`vehicle.id`** (N:1, optionnel, **ON DELETE SET NULL**) — un événement plaque peut référencer un véhicule connu (ou null si plaque inconnue) ; supprimer un véhicule n'efface pas l'historique d'événements. 🟢
- `refresh_tokens.user_id` → **`user.id`** (N:1) — un utilisateur possède plusieurs jetons (multi-appareils). 🟢
- **Pas de relation directe** `people` ↔ `user` ni `vehicle` ↔ `user` (les personnes/véhicules surveillés ≠ utilisateurs de la plateforme). `people` et `vehicle` sont deux référentiels **symétriques et indépendants** (visages vs plaques). 🟢

### 7.3 Remarques
- Les embeddings sont stockés **en base** (`pgvector`) **et** chargés en mémoire dans **FAISS** au démarrage du backend — FAISS sert de moteur de recherche rapide ; pgvector est la source de vérité persistante. 🟢
- ⚠️ Le `phone` et l'`email` de `people` sont `unique` et **non nullables** → contrainte forte à signaler (peut bloquer l'enrôlement de personnes inconnues). 🟢
- La recherche floue de plaques (`/plates/search`) charge **toutes** les lignes `vehicle` et calcule la similarité de Levenshtein **en Python** (O(N) par requête, après un court-circuit sur match exact indexé). Suffisant pour des centaines/milliers de plaques ; au-delà, prévoir un index trigramme (`pg_trgm`) ou un pré-filtre SQL. 🟢 *(à signaler comme limite de passage à l'échelle, parallèle au rôle de FAISS pour les visages)*

---

## 8. Diagrammes à produire

> Pour chaque diagramme : (a) pourquoi il est nécessaire, (b) une version PlantUML prête à compiler, (c) ce que l'étudiant doit vérifier/adapter.
> **PlantUML** se compile sur https://www.plantuml.com/plantuml ou via l'extension VS Code « PlantUML ».

### 8.1 Diagramme de cas d'utilisation
**Pourquoi** : montre les acteurs (rôles) et les fonctionnalités offertes — pose le périmètre fonctionnel du système, indispensable au chapitre « analyse des besoins » du mémoire.

```plantuml
@startuml
left to right direction
skinparam actorStyle awesome

actor "Admin" as admin
actor "User (opérateur)" as user
actor "Viewer" as viewer
actor "Caméra RTSP" as cam
actor "Core (service IA)" as core

rectangle "Plateforme Osirion" {
  usecase "S'authentifier (JWT)" as UC_auth
  usecase "Gérer les utilisateurs" as UC_users
  usecase "Gérer les caméras (CRUD)" as UC_cam
  usecase "Enrôler une personne\n(1 ou plusieurs images)" as UC_enroll
  usecase "Rechercher par visage" as UC_search
  usecase "Consulter le flux live" as UC_live
  usecase "Consulter les événements" as UC_events
  usecase "Superviser l'état système" as UC_sys
  usecase "Détecter & reconnaître\nles visages (temps réel)" as UC_reco
  usecase "Détecter & lire\nles plaques (LPR/ANPR)" as UC_plate
  usecase "Gérer les plaques\n(véhicules surveillés)" as UC_plates_mgmt
  usecase "Journaliser un événement" as UC_logevent
  usecase "Lever une alerte\n(blacklist)" as UC_alert
}

admin --> UC_auth
user --> UC_auth
viewer --> UC_auth
admin --> UC_users
admin --> UC_cam
user --> UC_cam
admin --> UC_enroll
user --> UC_enroll
viewer --> UC_live
viewer --> UC_events
admin --> UC_sys

cam --> UC_reco
core --> UC_reco
UC_reco ..> UC_search : <<include>>
UC_reco ..> UC_logevent : <<include>>
core --> UC_logevent

admin --> UC_plates_mgmt
user --> UC_plates_mgmt
cam --> UC_plate
core --> UC_plate
UC_plate ..> UC_logevent : <<include>>
UC_plate ..> UC_alert : <<extend>>
@enduml
```
**À vérifier / adapter** 🔴 : confirmer les droits exacts de `viewer` (peut-il voir le live ? — oui via `require_viewer` sur `/cameras` et `/plates` en lecture) ; l'écriture des plaques (`add/update/delete/blacklist`) est réservée à `user`+/`admin`.

### 8.2 Diagramme de classes
**Pourquoi** : représente le modèle de données et les principales classes du Core — montre la conception orientée objet et le schéma relationnel.

```plantuml
@startuml
skinparam classAttributeIconSize 0

' ---- Modèle de données (backend) ----
class User {
  +id: int
  +fullName: str
  +email: str
  +usr_password: str
  +role: str
  +is_active: bool
  +failed_login_attempts: int
  +locked_until: datetime
}
class RefreshToken {
  +id: int
  +token: str
  +expires_at: datetime
  +is_revoked: bool
}
class People {
  +id: int
  +first_name: str
  +last_name: str
  +phone: str
  +email: str
  +image_url: str
  +embeddings: Vector(512)
}
class Camera {
  +id: int
  +cam_name: str
  +rtsp_url: str  <<chiffré>>
  +location: str
  +is_active: bool
}
class Event {
  +id: int
  +event_type: str
  +confidence: float
  +snapshot_url: str
  +plate_text_detected: str
  +vehicle_id: int
  +timestamp: datetime
}
class Vehicle {
  +id: int
  +plate_text: str <<unique>>
  +owner_name: str
  +is_blacklisted: bool
  +notes: str
}

User "1" o-- "*" RefreshToken
Camera "1" o-- "*" Event
People "1" o-- "*" Event
Vehicle "1" o-- "*" Event

' ---- Composants Core (surveillance) ----
class SurveillanceSystem {
  +initialize_cameras()
  +start_camera_threads()
  +run()
  +stop()
}
class CameraCapture {
  +run()
  +connect_camera()
  +handle_reconnection()
}
class TrackingProcessor {
  +run()
  +prepare_detections()
  +process_recognitions()
  +update_person_database()
}
class GlobalPersonTracker {
  +find_person_by_embedding()
  +find_or_register()
  +update_person_location()
}
class AdaptiveThreshold {
  +observe(score)
  +value
}
class WebStreamingServer {
  +start()
  +_broadcast_camera()
}
class PlateProcessor {
  +process()
  +annotate_cached()
  +shutdown()
}
class RuntimeControl {
  +lpr_enabled: bool
  +set_lpr(enabled)
}

SurveillanceSystem "1" *-- "*" CameraCapture
SurveillanceSystem "1" *-- "*" TrackingProcessor
SurveillanceSystem "1" *-- "1" GlobalPersonTracker
SurveillanceSystem "1" *-- "1" WebStreamingServer
SurveillanceSystem "1" *-- "1" RuntimeControl
TrackingProcessor "1" *-- "1" AdaptiveThreshold
TrackingProcessor "1" o-- "0..1" PlateProcessor
TrackingProcessor ..> GlobalPersonTracker
TrackingProcessor ..> RuntimeControl
@enduml
```
**À vérifier / adapter** 🔴 : ajouter les méthodes que tu juges importantes ; si tu veux un diagramme purement « base de données », garder seulement les 6 entités du haut (User, RefreshToken, People, Camera, Event, **Vehicle**). Vérifier les cardinalités `People–Event` et `Vehicle–Event` (un événement peut avoir `person_id`/`vehicle_id` null → relation 0..1 côté People/Vehicle).

### 8.3 Diagramme de séquence (reconnaissance temps réel)
**Pourquoi** : c'est **le cœur du système** — il illustre la collaboration caméra → core → backend → DB lors d'une reconnaissance, et la place du cache global.

```plantuml
@startuml
actor "Caméra RTSP" as Cam
participant "CameraCapture" as Cap
participant "TrackingProcessor" as Proc
participant "InsightFace\n(SCRFD+ArcFace)" as IF
participant "ByteTrack" as BT
participant "GlobalPersonTracker" as GPT
participant "Backend\n/people/search" as API
database "PostgreSQL\n+ FAISS" as DB
participant "WebStreamingServer" as WS
actor "Navigateur" as Web

Cam -> Cap : flux RTSP
Cap -> Proc : frame (queue)
Proc -> Proc : filtre flou (Laplacien)
Proc -> IF : detect_faces_with_embeddings(frame)
IF --> Proc : [(bbox, conf, embedding512)]
Proc -> BT : update(détections)
BT --> Proc : tracks (track_id)
loop pour chaque track à (ré)identifier
  Proc -> GPT : find_person_by_embedding(emb)
  alt Cache HIT
    GPT --> Proc : person_id, name, score
  else Cache MISS
    Proc -> API : POST /people/search (emb)
    API -> DB : recherche cosinus FAISS
    DB --> API : top-1 {name, score}
    API --> Proc : résultat
    Proc -> GPT : find_or_register(...)
    Proc -> API : POST /events/add (snapshot, score)
    API -> DB : INSERT event
  end
end
Proc -> WS : result_frames[cam_id] (annotée)
Web -> WS : start_stream {camera_id}
WS --> Web : frame (JPEG base64) @~30 FPS
@enduml
```
**À vérifier / adapter** 🔴 : le `POST /events/add` n'est émis **que** lors d'une reconnaissance via API (pas sur cache hit) → adapte si tu changes ce comportement. Tu peux ajouter un fragment montrant la ré-authentification JWT du Core (HTTP 401 → refresh).

### 8.4 Diagramme de déploiement
**Pourquoi** : montre la répartition physique/conteneurs, les ports, le GPU et les protocoles réseau — essentiel pour le chapitre « architecture technique / déploiement ».

```plantuml
@startuml
node "Serveur hôte (Docker + nvidia-container-toolkit)" {
  node "Réseau Docker 'osirion'" {
    [frontend\nNext.js :3000] as FE
    [backend\nFastAPI :8000\n(GPU)] as BE
    [core\nFlask :5000\n(GPU)] as CORE
    database "db\nPostgreSQL 15\n+ pgvector" as DB
  }
}
node "GPU NVIDIA" as GPU
cloud "Caméras IP\n(RTSP)" as CAMS
actor "Navigateur\n(opérateur)" as USER

USER --> FE : HTTP :3000
USER --> CORE : WebSocket :5000 (socket.io)
FE --> BE : HTTP REST (SSR proxy)
CORE --> BE : HTTP REST (JWT)
BE --> DB : SQL (psycopg2)
CORE --> CAMS : RTSP/TCP
BE ..> GPU : ONNX Runtime CUDA
CORE ..> GPU : ONNX Runtime CUDA
@enduml
```
**À vérifier / adapter** 🔴 : préciser si backend et core partagent **le même GPU** (le compose réserve 1 GPU à chacun ; sur une seule carte ils la partagent) ; indiquer l'OS/host réel et si un reverse proxy (Nginx) est utilisé en production (recommandé dans le README mais non fourni).

### 8.5 Diagramme d'activité (traitement d'une frame)
**Pourquoi** : décrit la logique algorithmique de décision (flou, détection, cache, seuil) — utile pour expliquer le « comportement » du système au jury.

```plantuml
@startuml
start
:Lire frame depuis la queue;
if (frame_counter % N == 0 ?) then (oui)
  :Calculer netteté (Laplacien);
  if (netteté < seuil flou ?) then (oui)
    :Réutiliser dernières annotations;
    :Diffuser frame;
    stop
  else (non)
  endif
  :Détection SCRFD + embedding ArcFace (GPU);
  :Mettre à jour ByteTrack;
  partition "Pour chaque track à (ré)identifier" {
    :Chercher dans cache global;
    if (cache HIT ?) then (oui)
      :Mettre à jour localisation\n(person_id existant);
    else (non)
      :POST /people/search (FAISS);
      if (score > seuil adaptatif ?) then (oui)
        :find_or_register (person_id);
        :POST /events/add (snapshot);
      else (non)
        :Marquer "Inconnu";
      endif
    endif
  }
  :Annoter bounding boxes;
  :Nettoyer cache expiré (périodique);
else (non)
  :Ré-appliquer dernières annotations;
endif
:Ajouter overlay caméra;
:Stocker dans result_frames;
:Diffuser via WebSocket;
stop
@enduml
```
**À vérifier / adapter** 🔴 : `N = PROCESS_EVERY_N_FRAME` (3 en GPU, 10 dans le `main.py` legacy) ; ajuste la valeur citée dans ton mémoire selon la config réellement déployée.

### 8.6 Diagramme de séquence (reconnaissance de plaque — LPR)
**Pourquoi** : illustre le **2e module** et son optimisation phare — la **résolution réseau découplée** (worker dédié) qui empêche la latence backend de figer le flux vidéo.

```plantuml
@startuml
actor "Caméra RTSP" as Cam
participant "TrackingProcessor" as Proc
participant "PlateProcessor" as PP
participant "YOLO\n(détection plaque)" as YOLO
participant "ByteTrack\n(plaques)" as BT
participant "EasyOCR" as OCR
queue "File FIFO" as Q
participant "Worker réseau\n(thread dédié)" as W
participant "Backend\n/plates/search · /events/add" as API
database "PostgreSQL\n(vehicle, event)" as DB

Cam -> Proc : frame (déjà traitée par le facial)
Proc -> PP : process(frame)  [si LPR activé]
PP -> YOLO : detect_plates (1 frame / N)
YOLO --> PP : bboxes plaques
PP -> BT : update(détections)
BT --> PP : tracks (track_id)
loop pour chaque track non finalisé
  PP -> OCR : read_plate_text(crop)
  OCR --> PP : (texte, conf)
  PP -> PP : vote temporel (consensus)
end
PP -> Q : job {plaque finalisée + snapshot}
PP --> Proc : frame annotée (boîtes plaques)
== Résolution asynchrone — ne bloque jamais la caméra ==
W -> Q : get(job)
W -> API : POST /plates/search (fuzzy, seuil 0.82)
API -> DB : SELECT vehicles + similarité Levenshtein
DB --> API : meilleur match {vehicle_id, blacklist, score}
API --> W : résultat
alt plaque blacklistée
  W -> W : 🚨 ALERTE (log)
end
W -> API : POST /events/add (PLATE_RECOGNITION, snapshot)
API -> DB : INSERT event
W --> PP : résultat (appliqué aux frames suivantes)
@enduml
```
**À vérifier / adapter** 🔴 : la recherche est exécutée par un **thread worker** distinct du thread caméra (file FIFO) ; insiste sur ce point au jury (découplage I/O réseau ↔ traitement temps réel). L'événement n'est émis qu'**une fois** par track (`event_sent`).

---

## 9. Points faibles et limites

> Observations factuelles tirées du code. 🟢 sauf mention contraire.

**Architecture & cohérence**
1. **Module plaques (LPR) : OCR non benchmarké** — le module est complet et fonctionnel (cf. §6), mais sa précision OCR n'est validée par **aucun benchmark chiffré** dans le dépôt, et la config OCR (langue `en`, allowlist générique) doit être **adaptée au format local** des plaques (un `PLATE_FORMAT_REGEX` est prévu pour ça). 🔴
2. **Double code Core** : `main.py` (monolithe legacy) vs `main_refactored.py` (modulaire) + `face_detection.py` vs `face_detection_new.py` → confusion, dette technique. Il faut documenter lequel fait foi (`main_refactored.py`).
3. **Incohérence documentation/code (facial)** : le README annonce « détection YOLOv11n » pour les **visages**, mais le pipeline facial réel utilise SCRFD (InsightFace) ; `detection_service.py` (YOLO) du backend semble inutilisé. *(NB : YOLO est en revanche bien utilisé par le **nouveau module plaques**, ce qui peut prêter à confusion entre les deux usages de YOLO.)* 🟡

**Robustesse & passage à l'échelle**
4. **Cache global purement en mémoire** (perdu au redémarrage, non partagé entre plusieurs instances Core). Pas de Redis.
5. **FAISS reconstruit en RAM au démarrage** : pas de persistance de l'index ; sur grand volume, la reconstruction peut être coûteuse.
6. **Threading Python (GIL)** : 2 threads/caméra ; la scalabilité au-delà de quelques caméras dépend fortement du GPU (cf. tableaux de perf du README, non benchmarkés ici 🔴).
7. **Pas de file de messages** entre Core et Backend (appels HTTP synchrones/asynchrones directs) → couplage et sensibilité à la latence réseau.

**Sécurité**
8. **WebSocket & routes REST du Core non authentifiés** (TODO README) : n'importe quel client autorisé par CORS peut s'abonner aux flux vidéo → fuite vidéo potentielle. De même, les routes `GET /api/lpr/status` et `POST /api/lpr/toggle` du Core ne sont **pas protégées par JWT** — un client même-origine peut activer/désactiver le LPR (à cloisonner si le Core est exposé). 🟢
9. **CORS par défaut permissif** : `BACKEND_CORS_ORIGINS = ["*"]` côté backend par défaut ; côté Core, fallback `'*'` si non configuré (avec avertissement).
10. **Compte de service Core** : identifiants `AUTH_EMAIL`/`AUTH_PASSWORD` en `.env`, droits élevés ; à cloisonner.
11. **Secrets dans `.env`** committé ? (présence d'un `.env` à la racine — 🔴 vérifier qu'il n'est pas versionné avec de vraies clés).

**Fonctionnel**
12. **Événements ENTRY/EXIT/DETECTION** déclarés mais non générés.
13. **`people.phone`/`email` uniques et obligatoires** : modèle inadapté pour surveiller des personnes dont on n'a pas ces données.
14. **Blacklist faciale & `alerts`** : la *blacklist* **plaques** est fonctionnelle (table `Vehicle.is_blacklisted` + endpoint + alerte log) ; en revanche une *blacklist*/`alerts` **faciale** (par personne) reste sans table/endpoint dédié, et aucune **alerte temps réel poussée** au frontend n'existe (l'alerte blacklist plaque est seulement journalisée côté Core). 🟡
15. **Vérification email & reset password** non finalisés (TODO).
16. **Pas de tests** côté Core (quelques tests backend `tests/` existent : faiss, enrollment, embedding). 🟢
17. **Risque de faux positifs** inhérent à la reconnaissance faciale (jumeaux, mauvais éclairage) — le seuil adaptatif atténue mais ne supprime pas.

**Données & vie privée**
18. **Aspect RGPD/éthique** : stockage de **données biométriques** (embeddings faciaux) **et de plaques d'immatriculation** (donnée à caractère personnel) — un mémoire doit traiter le cadre légal (consentement, base légale, finalité, durée de conservation, proportionnalité de la surveillance). 🟡

---

## 10. Pistes d'amélioration

**Court terme (consolidation de l'existant)**
- Supprimer le code legacy (`main.py`, `face_detection_new.py` si inutilisé) et aligner README ↔ code.
- Authentifier le WebSocket du Core par JWT (déjà prévu).
- Restreindre les CORS en production ; externaliser/roter les secrets (Vault, secrets Docker).
- Générer réellement les événements `ENTRY`/`EXIT` (logique d'apparition/disparition de track) et `DETECTION`.
- Ajouter des tests automatisés sur le Core (pipeline, tracker global, seuil adaptatif).

**Module plaques (✅ livré — cf. §6) — pistes d'évolution**
- Sauvegarder le **crop de la plaque** (pas seulement le snapshot de la frame entière) pour audit/preuve.
- Ajouter un **benchmark OCR chiffré** (précision par condition : jour/nuit, angle, distance, vitesse) avec un jeu de tests dédié.
- **Profil régional** : OCR multilingue + `PLATE_FORMAT_REGEX` adapté au format local des plaques visées.
- **Alerte temps réel poussée** au frontend (WebSocket) sur détection blacklist, en complément du log Core.
- Enrichir `Vehicle` (marque/modèle/couleur) et **corréler plaque ↔ visage** (associer conducteur et véhicule dans un même événement).
- **Authentifier les routes `/api/lpr/*`** du Core (JWT), comme prévu pour le WebSocket.

**Performance & scalabilité**
- Persister le cache global et l'index FAISS (Redis / disque) ; index FAISS GPU (`faiss-gpu`).
- Architecture distribuée : workers GPU + file de messages (Kafka/RabbitMQ) entre capture et inférence.
- Batching d'inférence multi-caméras pour saturer le GPU.

**Observabilité**
- Métriques Prometheus + dashboards Grafana (le code émet déjà des logs JSON structurés `osirion.monitoring` exploitables).
- Traçabilité des trajectoires (`/api/persons/{id}/trajectory`) déjà esquissée dans la doc.

**Fonctionnel & UX**
- Module d'alertes temps réel (push WebSocket vers le frontend lors d'une reconnaissance « blacklist »).
- Recherche/filtre avancé d'événements (par personne, caméra, période).
- Gestion fine du consentement et de la conservation des données biométriques (RGPD).

---

### Annexe — Inventaire des fichiers clés analysés
- **Core** : `main_refactored.py`, `main.py`, `config/settings.py`, `core/{surveillance_system,camera_manager,tracking_processor,global_person_tracker,adaptive_threshold,web_streaming}.py`, `face_detection.py`, `services/{embeddings_search_service,event_services,camera_fetching_service}.py`, `utils/auth_utils.py`.
  - **LPR (module plaques)** : `plate_detection.py`, `core/plate_processor.py`, `core/runtime_control.py`, `services/plate_search_service.py`, intégration dans `core/tracking_processor.py` et routes `/api/lpr/*` dans `core/web_streaming.py`, modèle `license_plate_detector.pt`.
- **Backend** : `app/main.py`, `app/config.py`, `app/models/{users,people,cameras,events}.py`, `app/services/{embeddings_service,Faiss_search_service,detection_service,recognition_service}.py`, `app/routes/{auth,people,cameras,events,monitoring}_routes.py`, `app/middleware/auth_middleware.py`, `app/utils/security_utils.py`, `alembic/versions/*`.
  - **LPR (module plaques)** : `app/models/vehicles.py`, `app/routes/plates_routes.py`, `app/utils/plate_utils.py`, `app/schemas/vehicles_schema.py`, migration `c3d4e5f6a7b8_add_vehicle_and_plate_event_fields.py`.
- **Frontend** : `package.json`, `app/Osirion/admin/live/CameraStream.js`, `app/Osirion/admin/settings/page.js`, **`app/Osirion/admin/plates/page.js`**, **`app/api/plates/*`**, `app/Osirion/admin/AdminSidebar.js`, arborescence `app/api/*` et `app/Osirion/admin/*`.
- **Déploiement** : `docker-compose.yml` (racine), `requirements*.txt` (ajouts `ultralytics`, `easyocr`, `rapidfuzz`), `Dockerfile` du Core (modèles YOLO/EasyOCR embarqués).

> ⚠️ **Fichiers non encore lus en détail** (à parcourir si besoin de plus de précision) : `face_detection_new.py`, pages frontend `blacklist/`, `alerts/`, `cameras/`, `users/`, `system-status/`, `users_routes.py`, `sys_monitoring_service.py`, schémas Pydantic (`app/schemas/*`). Niveau de confiance sur ces zones : 🟡/🔴.

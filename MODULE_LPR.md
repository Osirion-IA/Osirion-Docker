# Module LPR / ANPR — Reconnaissance des plaques d'immatriculation

> Module ajouté sur la branche `feature/license-plate-recognition`.
> Conçu pour s'intégrer **en parallèle** du pipeline de reconnaissance faciale
> existant, **sans jamais le perturber** (activation opt-in, dégradation gracieuse).

---

## 1. Vue d'ensemble

Le module LPR reproduit, pour les **véhicules**, la logique du module facial :

| | Facial (existant) | Plaques (nouveau) |
|---|---|---|
| Détection | SCRFD (InsightFace) | **YOLO** (Ultralytics) |
| « Signature » | Embedding ArcFace 512D | **Texte OCR** (EasyOCR) |
| Référentiel | Table `people` (pgvector) | Table **`vehicle`** (texte normalisé) |
| Recherche | Similarité cosinus (FAISS) | **Fuzzy matching** (Levenshtein + repli OCR) |
| Suivi | ByteTrack (par caméra) | **ByteTrack** dédié (par caméra) |
| Événement | `event_type=RECOGNITION` | `event_type=PLATE_RECOGNITION` |

---

## 2. Flux de données

```
Caméra RTSP ─▶ Core (TrackingProcessor)
                 │  (sur chaque frame traitée, si LPR activé)
                 ▼
        PlateProcessor.process()
                 │ 1. YOLO  → bboxes de plaques
                 │ 2. ByteTrack (tracker plaques dédié) → track_id stables
                 │ 3. OCR EasyOCR (FRAME-SKIPPING : 1 lecture par track puis cache)
                 │ 4. POST /plates/search (backend)  ── fuzzy match ──▶ Vehicle
                 │ 5. POST /events/add (PLATE_RECOGNITION, plate_text, vehicle_id)
                 │ 6. annotation (boîte jaune/bleu/rouge + texte) incrustée au JPEG
                 ▼
        WebSocket 'frame' ─▶ Frontend (canvas) : la boîte plaque apparaît dans le flux
```

**Optimisation OCR (frame-skipping)** : l'OCR — coûteux — n'est lancé que tant
qu'un `track_id` n'a pas de lecture « définitive » (confiance ≥
`PLATE_OCR_GOOD_CONFIDENCE`) et sous `PLATE_OCR_MAX_ATTEMPTS`. Une fois la plaque
lue, le texte est **mis en cache pour ce track** et l'OCR est **totalement sauté**
sur les frames suivantes → réutilisation du texte mémorisé.

---

## 3. Fichiers ajoutés / modifiés

### Backend (`Osirion-backend-main/.../app/`)
- `models/vehicles.py` *(nouveau)* — table `Vehicle` (plaque normalisée unique, owner, blacklist, notes).
- `models/events.py` — `Event` étendu : `plate_text_detected`, `vehicle_id` (FK), constantes `EVENT_*`.
- `schemas/vehicles_schema.py` *(nouveau)* — Create/Update/Read + Search.
- `schemas/events_schema.py` — champs plaque ajoutés.
- `utils/plate_utils.py` *(nouveau)* — normalisation + **fuzzy matching** (rapidfuzz, fallback pur-Python).
- `routes/plates_routes.py` *(nouveau)* — CRUD + `POST /plates/search` (fuzzy).
- `routes/events_routes.py` — `/events/add` accepte `plate_text_detected`, `vehicle_id`.
- `main.py` — router `/plates` enregistré.
- `alembic/versions/c3d4e5f6a7b8_*.py` *(nouveau)* — table `vehicle` + colonnes plaque sur `event`.
- `alembic/env.py` — `Vehicle` importé.
- `requirements*.txt` — `rapidfuzz` ajouté.

### Core (`Osirion-core-master/.../`)
- `plate_detection.py` *(nouveau)* — singletons YOLO + EasyOCR, dégradation gracieuse (`LPR_AVAILABLE`).
- `core/plate_processor.py` *(nouveau)* — détection + tracking + OCR caché + lookup + annotation, par caméra.
- `core/runtime_control.py` *(nouveau)* — drapeau LPR thread-safe (toggle runtime).
- `core/tracking_processor.py` — intègre le LPR en parallèle du facial (lazy-init, gated).
- `core/surveillance_system.py` — crée `RuntimeControl`, le passe aux processeurs.
- `core/web_streaming.py` — endpoints `GET /api/lpr/status`, `POST /api/lpr/toggle` (+ CORS `/api/*`).
- `services/plate_search_service.py` *(nouveau)* — appel async `/plates/search`.
- `services/event_services.py` — `send_plate_event_async` ajouté.
- `config/settings.py` — bloc de config LPR + `PLATE_RECOGNITION` dans `EVENTS`.
- `requirements*.txt` — `easyocr` (+ `ultralytics`/`Flask-Cors` côté CPU).
- `Dockerfile` / `docker-compose.yml` — `plate_detection.py` embarqué + variables LPR.

### Frontend (`Osirion-front-end-main/.../app/`)
- `Osirion/admin/settings/page.js` — toggle « Plaques » câblé au Core (`/api/lpr/toggle` + statut au montage).
- `Osirion/admin/live/CameraStream.js` — badge « LPR actif » + légende des couleurs.

---

## 4. API backend

| Méthode | Route | Rôle requis | Description |
|---------|-------|-------------|-------------|
| POST | `/plates/add` | user/admin | Enregistrer une plaque (normalisée, unique) |
| GET | `/plates/` | viewer+ | Lister (option `blacklisted_only`) |
| GET | `/plates/{id}` | viewer+ | Détail |
| PUT | `/plates/update/{id}` | user/admin | Modifier |
| POST | `/plates/blacklist/{id}?blacklisted=true` | user/admin | (Dé)marquer blacklist |
| DELETE | `/plates/delete/{id}` | user/admin | Supprimer |
| POST | `/plates/search` | viewer+ | **Recherche floue** d'une plaque OCR |

Exemple `POST /plates/search` :
```json
{ "plate_text": "1ABC234", "threshold": 0.82, "k": 1 }
→ { "query": "1ABC234", "matched": true,
    "results": [ { "id": 7, "plate_text": "1ABC234", "owner_name": "…",
                   "is_blacklisted": false, "score": 1.0, "exact": true } ] }
```

---

## 5. Mise en service

### 5.1 Fournir un modèle de détection de plaque ⚠️ REQUIS
Le module a besoin d'un modèle **YOLO** entraîné à détecter les plaques
(`.pt` Ultralytics). Il n'est **pas** fourni (poids volumineux, hors dépôt).

Options :
- Télécharger un modèle public (ex. « license plate detector » YOLOv8/YOLOv11 sur
  Roboflow / Ultralytics HUB) et le placer dans le répertoire du Core sous
  `license_plate_detector.pt`, **ou**
- définir `PLATE_MODEL_PATH` vers son emplacement.

> Sans ce fichier, le Core démarre normalement, le **facial fonctionne**, et le LPR
> se signale « indisponible » (badge ⚠ dans le frontend).

### 5.2 Activer le module
- Soit `ENABLE_PLATE_RECOGNITION=true` dans le `.env`,
- soit à chaud depuis **Paramètres → Détection → Plaques d'immatriculation** (le
  toggle appelle `POST /api/lpr/toggle` du Core).

### 5.3 Démarrer la stack
```bash
cp .env.example .env      # renseigner les valeurs
python build_images.py    # ou: docker compose build
docker compose up -d      # la migration Alembic c3d4e5f6a7b8 s'applique au boot du backend
docker compose logs -f core
```

### 5.4 Enregistrer des plaques surveillées
```bash
# (token admin obtenu via /auth/login)
curl -X POST http://localhost:8000/plates/add \
  -H "Authorization: Bearer <TOKEN>" -H "Content-Type: application/json" \
  -d '{"plate_text":"1-ABC 234","owner_name":"Dupont","is_blacklisted":true}'
```

---

## 6. État de validation

| Vérification | Statut |
|--------------|--------|
| Syntaxe Python (py_compile) backend + core | ✅ tous les fichiers compilent |
| Logique de fuzzy matching (O↔0, I↔1, S↔5…) | ✅ testée isolément (fallback pur-Python) |
| JSX frontend (revue manuelle) | ✅ structure équilibrée |
| Migration Alembic appliquée sur PostgreSQL | ⏳ **non exécutée ici** (ni Docker ni Postgres dans l'environnement) — s'applique automatiquement au démarrage du backend (`entrypoint.py → alembic upgrade head`) |
| Test bout-en-bout avec flux RTSP réel + modèle YOLO | ⏳ à réaliser par l'étudiant (nécessite GPU, modèle de plaque et caméra) |

### Test rapide du fuzzy matching (sans dépendances externes)
```bash
cd Osirion-backend-main/Osirion-backend-main
python3 -c "from app.utils.plate_utils import plate_similarity as s; \
print(s('ABC0','ABCO'), s('AB1C','ABIC'), s('ABC123','XYZ999'))"
# → 1.0 1.0 0.0   (confusions OCR tolérées, plaques distinctes rejetées)
```

---

## 7. Points d'attention / limites

- **Modèle de plaque non fourni** → à télécharger/entraîner (cf. §5.1).
- **Pré-traitement OCR** minimal : pour des plaques difficiles, ajouter un redressement
  de perspective et un seuillage adaptatif avant EasyOCR améliorerait la lecture.
- **Annotations côté serveur** : les boîtes de plaques sont incrustées dans le JPEG par
  le Core (comme les visages) ; le frontend les affiche sans rendu client supplémentaire.
- **`/api/lpr/toggle` non authentifié** (cohérent avec l'API streaming actuelle du Core,
  elle aussi non protégée par JWT — voir limites connues du projet).
- **Fuzzy O(n)** : `/plates/search` compare à toutes les plaques connues ; suffisant
  pour des milliers d'entrées, à indexer (trigram/pg_trgm) au-delà.

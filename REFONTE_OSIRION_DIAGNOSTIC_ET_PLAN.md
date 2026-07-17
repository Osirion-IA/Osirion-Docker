# OSIRION — Diagnostic d'architecture & Plan de migration
### Phase 0 — Analyse préalable (livrable pour validation, aucun code écrit)

> Ce document est le résultat de l'analyse exigée avant toute implémentation.
> Il cartographie l'existant, diagnostique le réutilisable / les points de douleur,
> mesure l'écart avec l'architecture cible, et propose un plan de migration par
> phases **sans régression**. Deux instructions du cahier des charges sont
> discutées avec un avis d'architecte argumenté (§4).

---

## 0. Résumé exécutif (TL;DR)

**Verdict :** OSIRION n'est PAS une base à refondre — c'est une base **saine, modulaire et déjà bien découplée** à faire **évoluer de façon additive**. La bonne nouvelle : une grande partie de l'« architecture cible » (Vision → Scene Model → Event → Analytics → Decision → Exposition) existe déjà partiellement. Le vrai manque n'est pas structurel, il est **fonctionnel** : l'intelligence **spatiale** (zones, comptage, files, occupation, heatmaps) et un **moteur de règles configurable**.

**Ce qui existe déjà et qu'il ne faut surtout pas jeter :**
- Découplage **vidéo / métadonnées** (WebRTC via MediaMTX + Socket.IO) → c'est déjà une ébauche de « Scene Model diffusé ». Architecture VMS professionnelle.
- Le principe **« une seule couche GPU »** est déjà respecté : seul le Core infère (facial + plaques), backend et frontend sont CPU.
- Un **Event store** (6 types d'événements), un **workflow d'alertes** (new → acknowledged → resolved) avec notifications email/webhook, des **KPI de tableau de bord**, des **groupes de caméras** (bascule module en masse), des champs **géo** (carte + cônes de champ de vision).
- Sécurité mûre : JWT + refresh rotatif, RBAC (admin/user/viewer), chiffrement Fernet des URL RTSP, audit log, rate-limiting.
- Schéma PostgreSQL **propre et migré** (9 migrations Alembic, pgvector multi-vecteurs, index).

**Les deux alertes d'architecte (à trancher avant de coder) :**
1. 🔴 **« Supprimer complètement le module LPR »** — le LPR **est** votre contribution de mémoire (chapitre 4, tableau 4.6, et il est pleinement opérationnel sur les 5 couches). Le supprimer détruit un livrable évalué. **Recommandation : ne pas supprimer — le transformer en plugin Vision** (il en a déjà toutes les propriétés : opt-in, hot-toggle, dégradation gracieuse). Voir §4.1.
2. 🟠 **« Refais complètement le schéma PostgreSQL »** — le schéma actuel est solide et migré ; une refonte complète est un **risque de régression pur, sans bénéfice**. **Recommandation : évolution additive** (ajouter `zone`, `track`, `analytics_kpi`, `rule`, `report` par migrations Alembic). Voir §4.2.

**Le vrai chantier de valeur** (dans l'ordre) : Scene Model enrichi → Zones → Event Engine spatial → Analytics (comptage/files/occupation/heatmap) → moteur de Règles → Dashboard opérationnel + reporting automatique.

---

## 1. Cartographie de l'architecture actuelle

### 1.1 Les 5 services

| Service | Techno | Rôle | GPU |
|---|---|---|---|
| `db` | PostgreSQL 15 + pgvector | Persistance + recherche vectorielle | — |
| `backend` | FastAPI (SQLModel, Alembic) | Auth, CRUD, enrôlement facial, FAISS, events, alertes, KPI | CPU |
| `core` | Flask + Socket.IO | Vision temps réel : RTSP → détection → tracking → reco facial (+ plaques) → **métadonnées JSON** | **GPU** |
| `mediamtx` | bluenviron/mediamtx | Proxy média : RTSP → WebRTC/WHEP (transport vidéo) | — |
| `frontend` | Next.js 15 (app router) | Dashboard admin, live WebRTC + overlay canvas | — |

### 1.2 Flux de données réel (tel qu'observé dans le code)

```
Caméras RTSP
   │
   ├──────────────► MediaMTX ──(WebRTC/WHEP)──► Frontend <video>   (transport vidéo)
   │                  ▲
   │  (1 seule        │ RTSP republié
   │   connexion      │
   │   physique)      │
   └──────────────► Core (GPU)
                     │  CameraCapture (thread/cam) → file de frames
                     │  TrackingProcessor (thread/cam) :
                     │    détection SCRFD → embedding ArcFace → OC-SORT → vote temporel
                     │    → cache global multi-caméra → recherche FAISS (locale ou HTTP)
                     │    [+ PlateProcessor : YOLO plaque → OCR EasyOCR → vote → fuzzy search]
                     │
                     ├──(Socket.IO 'metadata' JSON)──► Frontend <canvas> overlay
                     │        { camera_id, width, height, seq, detections:[{type,bbox,label,track_id,confidence,...}] }
                     │
                     └──(HTTP)──► Backend : POST /events/add, /people/search, /plates/search, GET /cameras ...
                                     │
                                     └──► PostgreSQL (events, people+embeddings, vehicles, alerts, ...)
```

**Observation clé :** le payload `metadata` diffusé par le Core **est déjà un Scene Model** — mais un Scene Model *pauvre* : liste de détections `bbox + label` par frame, sans position au sol, sans direction/vitesse, sans notion de zone. C'est exactement le point d'appui de la refonte.

### 1.3 Schéma de base de données (existant, 10 tables)

`user`, `refresh_tokens`, `people`, `person_embeddings` (pgvector 512-D, multi-vecteurs), `camera`, `cameragroup`, `camera_group_link` (N↔N), `vehicle` (LPR), `event` (6 types, colonnes plaque + FK véhicule), `alert` (workflow new/ack/resolved), `audit_log`.

Points forts : multi-vecteurs par personne, `effective_config = local ∧ groupes`, géo (`latitude/longitude/bearing`), alertes auto sur blacklist. **Aucune notion de zone, de trajectoire persistée, ni de KPI agrégé stocké.**

### 1.4 API backend (synthèse)

~13 routeurs : `auth`, `people`, `plates`, `cameras`, `groups`, `events`, `alerts`, `users`, `audit`, `dashboard`, `maintenance`, `monitoring`. RBAC systématique. Le Core appelle : `/people/search`, `/plates/search`, `/events/add`, `/cameras`, `/people/blacklist`, `/people/embeddings` (sync FAISS local), `/auth/login|refresh`. **Tout est en polling** (pas de push backend → Core).

### 1.5 Frontend (pages existantes)

Login, Dashboard (KPI + graphe 7 j + feeds), Caméras (CRUD), Cameras-health (FPS temps réel), Live (grille WebRTC + overlay), Plates, Blacklist (enrôlement facial multi-photos), Groups, Map (Leaflet), Events, Alerts (workflow), Reports (export CSV/Excel/PDF **manuel**), Users, Settings (toggles modules), System-status (GPU), Audit. Auth par cookies httpOnly + refresh proactif + logout inactivité. `CameraStream.js` (WebRTC + overlay) est **hautement réutilisable**.

---

## 2. Diagnostic : réutilisable / points de douleur / stable

### 2.1 Solide et directement réutilisable ✅
- **Transport vidéo/métadonnées découplé** (MediaMTX + Socket.IO) — fondation de la cible.
- **Composant `CameraStream.js`** (vidéo + overlay canvas) — réutilisable tel quel pour le dashboard opérationnel.
- **Auth / RBAC / audit / rate-limit / chiffrement RTSP** — niveau production, à conserver.
- **Enrôlement facial InsightFace + pgvector multi-vecteurs + FAISS** (backend CPU + réplique locale Core) — stable, performant, à conserver.
- **Groupes de caméras + config effective + géo** — briques réutilisables pour les zones et le multi-site.
- **Schéma migré + pipeline Docker (GPU core / CPU backend)** — découpage macro déjà correct.

### 2.2 Points de douleur (couplage, duplication) ⚠️
- **Logique métier dans le Vision Engine** : `TrackingProcessor` mélange détection + tracking + vote temporel + cache + **émission directe d'événements**. Le principe cible « le Vision Engine ne produit QUE le Scene Model, aucune logique métier » est **violé aujourd'hui**. C'est le principal refactor interne à faire.
- **Duplication** : `face_detection.py` vs `face_detection_new.py` (code mort) ; logique de **vote temporel dupliquée ×3** (facial, plaque, +décision).
- **Tout en polling** : blacklist (5 s), caméras (15 s), FAISS (15 s). Pas de bus d'événements / push.
- **Pas de Scene Model typé** : la structure métadonnées est un dict ad hoc reconstruit à chaque frame, non versionné, non testé en isolation.
- **Reporting manuel** (export à la demande) — pas de génération planifiée.
- **Decision Engine figé** : la logique blacklist→alerte est codée en dur (pas de règles if/then configurables).
- **Pas de multi-tenant** (mono-organisation).

### 2.3 Fonctionnalités stables (à ne pas régresser)
Reconnaissance faciale (détection, vote temporel, seuil adaptatif, cache multi-caméra), LPR (opt-in), streaming WebRTC + overlay, auth, CRUD caméras/personnes/véhicules, groupes, events, alertes + notifications, dashboard KPI, santé caméras, monitoring GPU.

---

## 3. Écart avec l'architecture cible (gap analysis)

| Moteur cible | Existe aujourd'hui ? | À construire |
|---|---|---|
| **Vision Engine** (seule couche GPU, ne produit que le Scene Model) | ✅ à ~80 % (Core infère déjà seul) — mais mélange logique métier | Extraire proprement : le Core produit un **Scene Model typé**, la logique reco/décision sort dans une couche dédiée |
| **Scene Model** (structure riche : position, direction, vitesse, zone, identité) | 🟡 proto (payload `metadata` = bbox+label) | **Enrichir** : point au sol, direction/vitesse (dérivés du track), appartenance zones, versionner + typer |
| **Event Engine** (événements métier spatiaux : ZONE_ENTERED, LINE_CROSSED, QUEUE_UPDATED…) | 🔴 quasi absent (le Core émet RECOGNITION/PLATE/UNKNOWN_FACE en direct ; ENTRY/EXIT/DETECTION déclarés mais inutilisés) | **Créer** un vrai Event Engine consommant le Scene Model |
| **Analytics Engine** (comptage, fréquentation, files, occupation, heatmap, temps de présence) | 🟡 KPI basiques (compteurs, série 7 j) | **Créer** l'essentiel : comptage E/S, occupation, files, heatmap, dwell time + agrégats stockés |
| **Decision Engine** (règles if/then configurables) | 🟡 workflow d'alertes blacklist codé en dur | **Généraliser** en moteur de règles configurable (UI) |
| **Exposition** (dashboard, API REST+WS, reporting, notifications) | ✅ mûre — mais dashboard « sécurité » et reporting manuel | **Étendre** : dashboard opérationnel + reporting **automatique** planifié |
| **Plateforme** (multi-tenant, SDK, plugins, marketplace) | 🔴 absent | Hors périmètre mémoire — post-projet |

**Conclusion du gap :** ~2 moteurs sur 6 sont à créer réellement (Event spatial, Analytics), 2 à enrichir (Scene Model, Decision), 2 déjà là (Vision, Exposition). Le socle est bon.

---

## 4. Deux recommandations d'architecte (avis argumenté)

### 4.1 🔴 LPR : ne PAS supprimer — le convertir en *plugin Vision*

Le cahier des charges demande le retrait total du LPR. **En tant qu'architecte, je le déconseille formellement dans le contexte du mémoire**, pour des raisons factuelles :

- Le LPR **est** votre contribution : **chapitre 4, tableau 4.6** du mémoire (CER mono-image vs vote temporel, exactitude plaque, latence, fuzzy search). `MODULE_LPR.md`, `MESURES.md`, `mesure.sh` l'instrumentent. Le supprimer = **supprimer un livrable évalué**.
- Il est **déjà exactement ce que la cible appelle un module/plugin** : `ENABLE_PLATE_RECOGNITION=false` par défaut, hot-toggle `/api/lpr/toggle`, dégradation gracieuse (si modèle/OCR absents → facial intact), pipeline symétrique du facial. **Il ne pollue pas l'architecture — il la valide.**
- Le supprimer laisserait du code orphelin (table `vehicle`, colonnes `event.plate_*`, dépendances `ultralytics`/`easyocr` ~500 Mo) et créerait des trous UI.

**Recommandation :** le **conserver** et, lors de la Phase A, le formaliser comme premier **plugin** du futur système de plugins Vision (détecteur + « reader » + type d'événement). Il devient la **preuve de généralisation** de l'architecture (facial et plaques = deux instances du même contrat), ce qui *renforce* le mémoire au lieu de l'affaiblir.

> Si le retrait est malgré tout voulu (ex. produit final sans plaques), le faire **sur une branche dédiée, réversible**, et **seulement après soutenance** — jamais sur le tronc qui porte le mémoire.

### 4.2 🟠 Base de données : évolution additive, pas refonte

« Refais complètement le schéma » = jeter 9 migrations, pgvector multi-vecteurs, groupes, géo, alertes, audit — tous **fonctionnels** — pour les réécrire à l'identique + un peu. C'est du **risque de régression pur**.

**Recommandation :** **étendre** par migrations Alembic additives :
- `zone` (polygone GeoJSON par caméra, type : comptage / occupation / file), 
- `zone_line` (lignes de comptage E/S),
- `track` (trajectoires persistées : camera_id, track_id, class, first/last_seen, path),
- `analytics_kpi` (agrégats : métrique, zone_id, granularité horaire/jour, valeur),
- `rule` (condition if/then → action), `rule_action_log`,
- `report` / `report_schedule` (reporting automatique).

Aucune table existante supprimée ⇒ **non-régression garantie par construction**.

---

## 5. Plan de migration par phases

> Principe directeur : **chaque phase est additive et livrable seule**. Les pipelines facial + LPR restent intacts à tout moment. Durées indicatives pour **1 développeur** (à ajuster selon échéance mémoire).

| Phase | Objectif | Livrables | Durée | Dépend de | Risque |
|---|---|---|---|---|---|
| **A. Fondations** (refactor interne invisible) | Faire respecter « Vision Engine = Scene Model only » | Scene Model **typé** (dataclass versionnée) produit par le Core ; extraction de la logique reco/décision hors du Vision Engine ; suppression code mort (`face_detection_new.py`), factorisation du vote temporel ; **retrait complet du LPR** (branche réversible, artefacts mémoire préservés — cf. §9) ; **tests golden** metadata avant/après | 1–2 sem | — | Moyen (cœur temps réel) |
| **B. Zones & Scene Model spatial** | Donner une sémantique spatiale | Table `zone`/`zone_line` + API CRUD + **éditeur de zones** (dessin polygone sur la vidéo, réutilise `CameraStream`) ; Scene Model enrichi : point au sol, direction, vitesse, appartenance zones | 2 sem | A | Faible |
| **C. Event Engine** | Transformer Scene Model → événements métier | Nouveau composant CPU (voir §6) : `ZONE_ENTERED/LEFT`, `LINE_CROSSED`, `ZONE_OCCUPANCY_CHANGED`, `QUEUE_UPDATED` ; table `track` ; events horodatés en DB | 2 sem | B | Faible |
| **D. Analytics Engine** | Indicateurs opérationnels | Comptage entrées/sorties/présents ; fréquentation (horaire/jour/mois/tendances) ; files (longueur, temps d'attente moy/max, saturation) ; occupation zones + **heatmap** + temps de présence ; agrégats stockés (`analytics_kpi`) via jobs de fond | 2–3 sem | C | Faible |
| **E. Decision Engine** | Règles configurables | Table `rule` + moteur if/then + UI de configuration ; généralise blacklist→alerte ; alertes saturation/surpeuplement + recommandations | 1–2 sem | C (D pour règles quantitatives) | Faible |
| **F. Exposition opérationnelle** | Dashboard + reporting | Dashboard opérationnel (compteurs live, heatmap, files, occupation, historique, recommandations) ; **reporting automatique** planifié (quotidien/hebdo/mensuel → PDF/Excel → email) ; extension notifications | 2 sem | D, E | Faible |
| **G. Plateforme** (post-mémoire, optionnel) | Commercialisation | Multi-tenant (org_id + row-level security), SDK, système de plugins formalisé, marketplace | — | F | Élevé |

**Chemin critique :** A → B → C → D → F. E se greffe après C (règles qualitatives) et s'enrichit après D (règles quantitatives). G est explicitement **hors mémoire**.

### Note sur l'organisation du code (structure cible §5 du cahier des charges)
La cible propose une arborescence `osirion/{vision,events,analytics,decision,...}`. **Ne pas fusionner les 3 services en un seul process** : le découpage macro actuel (Core **GPU** / backend **CPU** / frontend) *est déjà* la bonne réalisation du principe « une seule couche GPU ». On applique la structure par domaine **à l'intérieur** de chaque service, et l'Event/Analytics Engine devient soit un **module CPU du backend**, soit un **nouveau service léger `osirion-analytics`** (recommandé pour un découplage GPU/CPU net — cf. §6).

---

## 6. Décision d'architecture à prendre en Phase C : où tourne l'Event/Analytics Engine ?

Deux options (à trancher au début de la Phase C) :

- **Option 1 — module dans le backend** : plus simple, réutilise DB/auth ; risque de surcharger le backend CPU.
- **Option 2 — nouveau service `osirion-analytics`** (recommandé) : consomme le flux Scene Model (Socket.IO ou file Redis) émis par le Core, produit events + agrégats en DB. Découplage propre, scalable, aligné « traitements lourds en arrière-plan ». Coût : un 6ᵉ service.

*Décision différée* — non bloquante pour les phases A–B.

---

## 7. Stratégie anti-régression & tests

- **Tests golden Scene Model** : capturer les payloads `metadata` actuels sur séquences de référence ; after chaque refactor Phase A, diff bit-à-bit du comportement (facial + LPR).
- **Additif only** : aucune table/endpoint supprimé ; les nouvelles fonctionnalités sont opt-in (comme LPR).
- **Feature flags** par caméra/groupe (réutilise `effective_config`) pour activer zones/comptage progressivement.
- **Mesures mémoire préservées** : `measurements/metrics.jsonl` + tableaux 4.4/4.5/4.6 continuent de tourner (le LPR reste, cf. §4.1).
- **Tests d'intégration** : le backend a déjà `tests/` ; étendre. Ajouter des tests unitaires au Core (aujourd'hui quasi absents) sur le Scene Model et l'Event Engine (CPU, faciles à tester).
- **Migrations réversibles** : chaque migration Alembic avec `downgrade`.

---

## 8. Décisions requises avant de coder (validation)

1. **Objectif & échéance** : ce chantier sert-il d'abord à **renforcer le mémoire** (additif, sans risque), à préparer la **productisation** (refonte plus large, post-soutenance), ou **les deux** (progressif) ?
2. **LPR** : conserver comme plugin (recommandé) / retirer / décider plus tard ?
3. **Schéma DB** : évolution additive (recommandé) / refonte complète ?
4. **Priorité fonctionnelle** : quel(s) module(s) livrer en premier (comptage/fréquentation, files d'attente, occupation/heatmap, zones intelligentes) ?

> Rien ne sera implémenté avant votre validation de ce plan et de ces 4 points.

---

## 9. Décisions validées (2026-07-17) & plan ajusté

| Point | Décision retenue |
|---|---|
| **Objectif** | **Productisation post-soutenance** → refactor ambitieux accepté (multi-tenant, plugins à terme). On conçoit dès maintenant « produit », pas « prototype ». |
| **LPR** | **Retrait complet** (post-soutenance ⇒ décision cohérente : plateforme retail/banque/hôpital sans lecture de plaques). |
| **Schéma DB** | **Évolution additive** (migrations Alembic, rien de supprimé côté tables existantes non-LPR). |
| **Priorité fonctionnelle** | **Files d'attente** + **Comptage & fréquentation** en tête. |

### 9.1 Conséquence sur la priorité : Zones = prérequis technique
Les deux priorités choisies (files, comptage) reposent toutes deux sur les **primitives spatiales** : une file = une **zone** de file ; un comptage E/S = une **ligne** de comptage. La Phase B (Zones & lignes) reste donc le **socle obligatoire** avant D, même si elle n'a pas été cochée comme « livrable prioritaire ». Séquence ajustée :

**A (fondations + retrait LPR) → B (zones + lignes) → C (Event Engine : `LINE_CROSSED`, `QUEUE_UPDATED`) → D (Analytics : comptage/fréquentation + files) → E (règles : saturation) → F (dashboard opérationnel + reporting auto).**

### 9.2 Retrait du LPR — protocole de sécurité (non négociable)
Le retrait supprime du code **et** des tables, il est donc traité comme une opération à risque, **réversible** :
1. **Branche dédiée** (ex. `refactor/remove-lpr`) partant d'un HEAD propre — jamais un `rm` sur le tronc.
2. **Artefacts mémoire PRÉSERVÉS** (jamais touchés) : `Memoire_Osirion_CORRIGE_.docx`, `MODULE_LPR.md`, `MESURES.md`, le dossier `measurements/`, et **tout l'historique git** (le code LPR reste récupérable via l'historique et la branche `feature/license-plate-recognition`).
3. **Retrait par couche, en 1 commit atomique et documenté** : frontend (page plates, proxies, badges overlay, toggle settings) → core (`plate_detection.py`, `plate_processor.py`, `plate_search_service.py`, `runtime_control` LPR, endpoints `/api/lpr/*`, intégration `tracking_processor`, ~26 vars `PLATE_*`) → backend (`vehicles.py` modèle/schéma/routes, `plate_utils.py`) → docker-compose (`ENABLE_PLATE_RECOGNITION`, bind-mount `.pt`, vars `PLATE_*`).
4. **DB** : migration Alembic `downgrade`-able qui retire `event.plate_text_detected` + `event.vehicle_id` + table `vehicle` (ou, plus prudent : *déprécier* d'abord — colonnes laissées nullables, table conservée un temps — puis drop dans une 2ᵉ migration). À trancher au moment de la migration.
5. **Tests golden** : le payload `metadata` facial doit être **identique** avant/après (le retrait LPR ne touche pas le facial).

### 9.3 Impact « productisation » sur les fondations (Phase A)
Puisque l'objectif est produit (et non plus prototype), la Phase A intègre dès le départ deux préparations *conceptuelles* (sans les implémenter entièrement) :
- **Contrat de plugin Vision** : formaliser l'interface `détecteur → Scene Model` pour que le facial soit « juste un plugin » — rend l'ajout futur de modules (comptage objets, véhicules par couleur…) trivial, et documente proprement le *retrait* du LPR comme désactivation d'un plugin.
- **Point d'ancrage multi-tenant** : introduire (sans le peupler) la notion d'`organization_id` dans les nouvelles tables (`zone`, `analytics_kpi`, `rule`, `report`) pour ne pas avoir à re-migrer plus tard. Les tables existantes ne sont pas touchées à ce stade.


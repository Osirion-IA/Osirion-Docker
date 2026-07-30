# OSIRION / Qwiper Sentinel — Fonctionnalités du système

**Plateforme d'intelligence opérationnelle basée sur la vidéo — 100 % anonyme.**

> État au **2026-07-21**, branche `sentinel-stable`.
> Ce document décrit ce que le système **fait aujourd'hui**. La reconnaissance
> faciale et la lecture de plaques (LPR) ont été **entièrement retirées** : le
> système n'identifie personne, il analyse des **flux de personnes anonymes**.
>
> L'interface est désormais présentée sous la marque **« Qwiper Sentinel »**
> (rebrand front-end) ; le nom interne du projet, les routes et l'API restent
> « Osirion ».

---

## 1. Vue d'ensemble

Le système transforme des caméras IP en **capteurs de données opérationnelles** :
combien de personnes entrent/sortent, combien sont présentes dans une zone,
quelle est la longueur et le temps d'attente d'une file, y a-t-il un attroupement,
une présence hors des heures autorisées… le tout **sans reconnaître les individus**
(aucune biométrie, aucune identité stockée).

Cas d'usage type : points de **réception colis** / agences multi-sites (files aux
guichets), agences bancaires, commerces, hôpitaux, industrie, collectivités.

**Chaîne de valeur :**
```
Caméras (RTSP direct OU catalogue HikCentral) → Détection de personnes (YOLO)
   → Tracking → Scene Model anonyme → Zones & lignes → Événements
   → Analytics (KPIs, prévisions) → Règles → Alertes & notifications
```

---

## 2. Architecture (5 services)

| Service | Rôle | Techno |
|---|---|---|
| **db** | Persistance | PostgreSQL 15 |
| **backend** | API, auth, zones, règles, analytics, alertes, connecteur HikCentral | FastAPI (CPU) |
| **core** | Vision temps réel : détection + tracking + Event Engine | Flask + **GPU** |
| **mediamtx** | Transport vidéo (RTSP → WebRTC) + **transcodage** | MediaMTX |
| **frontend** | Interface d'administration « Qwiper Sentinel » | Next.js 15 |

**Principe de sobriété :** une **seule** couche GPU (le Core, une passe YOLO par
frame). Tout le reste (événements, analytics, règles) est du CPU léger, hors du
chemin critique vidéo. La vidéo affichée passe par WebRTC (décodage natif du
navigateur), séparée des métadonnées d'analyse (JSON via Socket.IO).

**Auth machine-à-machine :** le Core s'authentifie au backend par **clé de service**
(`X-API-Key`, sans expiration) → plus jamais de déconnexion sur token expiré ;
repli JWT email/mot de passe si la clé n'est pas définie.

---

## 3. Fonctionnalités par domaine

### 3.1 Acquisition & streaming vidéo
- **Deux sources de flux :**
  - **RTSP direct** (caméras IP / NVR), URL saisie manuellement (chiffrée au repos).
  - **Catalogue HikCentral Professional** (OpenAPI Gateway, auth AK/SK) : le backend
    **synchronise le catalogue** par site (areas → groupes, caméras → catalogue) et
    **résout une URL RTSP standard** (`rtsp_s`) à la demande. Synchro **périodique**
    (≈15 min, configurable) **+ bouton manuel** dans l'interface.
- **Activation paresseuse (catalogue HikCentral)** : les caméras sont importées
  **non traitées** (`is_active=false`). Une caméra ne devient « traitée » (ingérée
  + IA) que lorsqu'on la **configure** (1re zone/ligne). On évite ainsi d'ingérer
  des dizaines de caméras inutilement.
- **Prévisualisation avant configuration** : dans l'éditeur de Zones, sélectionner
  une caméra du catalogue crée un chemin MediaMTX de **preview** (transcodé, à la
  demande) → le flux live s'affiche **sans lancer le traitement**.
- **Transcodage HEVC → H.264** : les flux HikCentral sont en H.265 (non lu par le
  WebRTC navigateur). Le relais ffmpeg (dans MediaMTX) ré-encode en H.264 —
  encodeur **configurable** (défaut `libx264` CPU ; `h264_vaapi`/`qsv` si `/dev/dri`).
- **Ajout/retrait de caméras à chaud** : le Core réconcilie périodiquement la
  liste avec le backend — pas de redémarrage.
- **Reconnexion RTSP automatique** illimitée (backoff exponentiel) : une caméra qui
  retombe se reconnecte seule. **Bouton « Relancer »** (retry) pour les caméras
  HikCentral (ré-interroge la liaison agence, souvent instable).
- **MediaMTX** : une **seule** connexion à la caméra physique, republiée en
  **WebRTC** pour le navigateur et lue par le Core pour l'analyse. Chemins créés/
  supprimés dynamiquement par caméra (`cam<id>`), idempotents.
- **Filtre anti-flou** : une frame trop floue (variance Laplacien < seuil) est
  sautée (pas d'inférence inutile). Seuil à adapter à la résolution du flux (le
  sous-flux 360p HikCentral exige un seuil bas).

### 3.2 Vision Engine anonyme (le cœur GPU)
- **Détection de personnes** par YOLO, **modèle configurable** (`PERSON_MODEL_PATH`) :
  **yolo26n** par défaut (NMS-free, ~5 Mo, léger) ou **yolo26s** (~20 Mo, plus précis
  sur les silhouettes petites/occultées des scènes larges) — les deux sont
  embarqués dans l'image. FP16 sur GPU. Classe COCO « person » uniquement.
- **Tracking multi-objets OC-SORT** : chaque personne reçoit un **identifiant de
  suivi anonyme** (`track_id`) persistant entre les frames — jamais une identité.
- **Scene Model** produit à chaque frame et diffusé en JSON :
  `{ camera_id, width, height, detections: [{ track_id, bbox, foot (point au sol),
  velocity, zones[] }] }`.
- **Overlay temps réel** dans le navigateur : boîtes anonymes dessinées sur la
  vidéo (canvas), alignées automatiquement quelle que soit la résolution.
- **Dégradation gracieuse** : si le modèle ne charge pas, le flux vidéo continue.

### 3.3 Zones & lignes de comptage (configurables)
- **Éditeur visuel** (`Zones & comptage`) : **sélecteur de caméras groupé par site**
  (recherche + statut en ligne/hors-ligne + tag « catalogue »), le flux live (ou la
  preview) s'affiche, et on **dessine** par-dessus :
  - **Zones** (polygones) de type *occupation*, *file d'attente*, *attroupement*
    ou *générique*, avec un **seuil** optionnel ;
  - **Lignes de comptage** (segment) avec un **sens « entrée »** (in/out).
- **Coordonnées normalisées** [0,1] → un tracé reste valable même si la résolution
  change.
- Dessiner la 1re primitive **active** automatiquement une caméra HikCentral.

### 3.4 Event Engine (détection d'événements métier)
Calculé côté Core (CPU léger) à partir du Scene Model, émis en **fire-and-forget** :
- **`ZONE_OCCUPANCY_CHANGED`** — le nombre de personnes dans une zone change
  (throttlé). Snapshot joint à la transition 0→occupé.
- **`CROWD_DETECTED`** — occupation ≥ seuil, **soutenue N secondes** + snapshot.
- **`LINE_CROSSED`** — franchissement d'une ligne, avec le **sens** (entrée/sortie).
- **`ZONE_DWELL`** — **temps de présence** à la sortie d'une zone (temps d'attente).

### 3.5 Analytics (indicateurs opérationnels & prévisions)
Page **Analytique** (5 onglets) + endpoints, calculés **à la volée** depuis les
événements (toujours frais) :
- **Affluence** :
  - **Tendance journalière** entrées/sorties (graphe temporel avec survol) ;
  - **Profil horaire** (passages par heure, pic mis en évidence) ;
  - **Carte de chaleur** jour de semaine × heure (affluence moyenne) ;
  - **Prévision des prochaines heures** + **projection de fin de journée** à partir
    d'une **baseline statistique historique** par (jour, heure) — avec **indice de
    confiance** ;
  - **Recommandations** en langage décision (renforcer l'accueil au pic, etc.).
- **Sites & caméras** : classement des **sites** et **caméras les plus fréquentés**
  (entrées cumulées + occupation courante).
- **Files & attente** : longueur actuelle + **temps d'attente moyen / max** par file.
- **Occupation par zone** : moyenne / max / actuel.
- **Incidents** : **attroupements + alertes** — timeline journalière, répartition par
  **sévérité** / type / caméra, **taux de résolution** du workflow.
- **Comparaison période précédente** (deltas % WoW/DoD) + **export CSV**.

### 3.6 Moteur de règles & alertes (le système « agit »)
- **Règles configurables** (page `Règles & alertes`) : *SI un événement satisfait
  des conditions PENDANT une plage horaire ALORS créer une alerte (+ notifier)*.
  - **Déclencheur** : occupation, attroupement, franchissement, temps de présence.
  - **Conditions** : occupation min, temps d'attente min, sens.
  - **Plage horaire armée** : jours + heures, **gère le passage minuit** (intrusion).
  - **Sévérité** + **cooldown** (anti-spam) + restriction à une zone (optionnels).
- **Cas d'usage couverts** : intrusion horaire (+ photo + notif), attroupement /
  saturation guichet.
- **Alertes** : centre d'alertes avec **workflow** *nouveau → acquitté → résolu*,
  **pagination** serveur.
- **Notifications** : **email (SMTP)** et **webhook** — automatiques (par règle) ou
  manuelles (bouton sur une alerte).
- **Temps réel** : toast + son dans l'interface dès qu'une alerte est créée.

### 3.7 Caméras, groupes & cartographie
- **CRUD caméras** : nom, source (RTSP/HikCentral), URL RTSP (**chiffrée** au repos),
  localisation, activation/désactivation, géo-coordonnées (lat/lon + cap boussole).
- **Groupes de caméras / sites** : organisation du parc ; bascule de module en
  masse ; mappés aux **areas HikCentral** lors de la synchro.
- **Carte** (OpenStreetMap/Leaflet) : caméras géolocalisées + **cône de champ de
  vision**.
- **Santé des « caméras traitées »** : FPS, état (online / connecting / offline /
  stalled), reconnexions, uptime — **regroupée par site**, rafraîchie en temps réel,
  avec **bouton « Relancer »** sur les caméras HikCentral.

### 3.8 Dashboard, événements & rapports
- **Dashboard / Cockpit** : KPIs (caméras actives, événements, alertes), activité,
  aperçus live.
- **Journal d'événements** : filtrable par type / caméra, avec snapshots et contexte.
- **Rapports** : tableau filtrable (période, type) + **export CSV / Excel / PDF**
  (déclenché manuellement).

### 3.9 Sécurité & administration
- **Authentification JWT** (access 30 min + refresh 7 j, rotation) **+ clé de
  service M2M** (`X-API-Key`) pour le Core.
- **Rôles (RBAC)** : `admin`, `user`, `viewer` — appliqués backend **et** frontend.
- **Gestion des utilisateurs** (admin), **journal d'audit** (admin), **maintenance**
  (purge), **monitoring système** (CPU/RAM/disque + **GPU**).
- **Durcissements** : rate-limiting, verrouillage de compte, chiffrement Fernet des
  URL RTSP, CORS strict en production, cookies adaptés à l'accès LAN (HTTP).

### 3.10 Confidentialité / RGPD
- **Aucune donnée biométrique**, aucune reconnaissance faciale, aucune plaque.
- Les personnes sont des **objets anonymes** suivis le temps de leur passage.
- Argument de conformité fort : analyse opérationnelle **sans fichage nominatif**.

### 3.11 Zoom détaillé : les pages d'analyse

La section **« Analyser »** regroupe trois pages complémentaires : **Analytique**
(agrégats & prévisions), **Événements** (le détail brut) et **Rapports** (export).

#### a) Page « Analytique »
Un **sélecteur de période** (7 j / 30 j / 90 j) et un **export CSV** en tête.
Toutes les données sont **calculées à la volée** depuis la table `event`
(toujours fraîches). Un **indice de confiance** prévient quand l'historique est
trop mince pour fiabiliser les projections.

**Bandeau de KPIs (4 cartes, toujours visibles) :**
- **Aujourd'hui** — passages entrants du jour + **projection de fin de journée** et
  écart % vs une journée habituelle (même jour de semaine).
- **Entrées · période** — total sur la fenêtre + **delta % vs la période précédente**
  (flèche verte/rouge).
- **Heure de pointe** — créneau le plus chargé + nombre de passages.
- **Jour le plus chargé** — jour de semaine avec la plus forte moyenne.

**Onglet « Affluence » :**
- **Tendance journalière** — graphe temporel **entrées vs sorties** jour par jour ;
  survol de la courbe = détail d'une journée (date + valeurs). Lit l'évolution et
  détecte les ruptures.
- **Passages par heure** — histogramme du profil horaire, **pic mis en évidence**.
- **Prévision — prochaines heures** — nombre attendu aux heures à venir, d'après la
  **baseline historique** par (jour de semaine, heure). *Statistique, pas de ML.*
- **Recommandations** — phrases décisionnelles générées (renforcer l'accueil au pic,
  fenêtre creuse pour la maintenance, caméra la plus fréquentée…).
- **Carte de chaleur** — matrice **jour de semaine × heure** (affluence moyenne),
  échelle du clair au foncé → visualise les créneaux récurrents de forte affluence.

**Onglet « Sites & caméras » :**
- **Sites les plus fréquentés** — entrées cumulées par site (agence), classées.
- **Caméras les plus fréquentées** — entrées par caméra + **occupation courante**.
  Répond à « quelle agence / quel point est le plus sollicité ? ».

**Onglet « Files & attente » :**
- Tableau par zone de type *file* : **longueur actuelle**, **temps d'attente moyen**
  et **maximum**. Cœur du pilotage d'un hall à guichets.

**Onglet « Occupation » :**
- Barres d'**occupation courante par zone** (dernière valeur connue), normalisées.

**Onglet « Incidents » :**
- **4 KPIs** : nb d'alertes, nb d'attroupements, nb de critiques, **taux de
  résolution** du workflow.
- **Incidents par jour** — courbe **alertes vs attroupements** dans le temps.
- **Par sévérité** — répartition critique / avertissement / info (couleurs de statut).
- **Alertes par caméra** — classement des caméras génératrices d'alertes.

> Codes couleur : les séries d'affluence utilisent le bleu (primaire) et le gris ;
> les **couleurs de statut** (rouge/ambre/bleu) sont **réservées** aux incidents et
> à la sévérité, jamais recyclées comme « série n° 4 » — pour une lecture sans
> ambiguïté.

#### b) Page « Événements »
Le **journal brut** derrière les agrégats : chaque événement
(`LINE_CROSSED`, `ZONE_OCCUPANCY_CHANGED`, `CROWD_DETECTED`, `ZONE_DWELL`) avec son
horodatage, sa caméra, son contexte (zone, occupation, sens) et son **snapshot**.
Filtrable par type et par caméra. Sert la traçabilité et l'audit d'un chiffre.

#### c) Page « Rapports »
Tableau filtrable (période, type) avec **export CSV / Excel / PDF** déclenché
manuellement — pour partager ou archiver hors plateforme.

> **À retenir :** la fiabilité de *toutes* ces analyses dépend de la qualité de la
> détection en amont (un passage non détecté = un chiffre sous-estimé). La
> résolution du flux (360p vs 1440p) et le modèle (yolo26n vs yolo26s) sont donc les
> premiers leviers de justesse.

---

## 4. Interface (pages d'administration)

| Section | Page | Fonction |
|---|---|---|
| Surveiller | Cockpit | KPIs + activité + aperçus |
| Surveiller | Mur de caméras (Live) | grille de flux WebRTC + overlay |
| Surveiller | Centre d'alertes | workflow + notif (paginé) |
| Analyser | **Analytique** | affluence, sites/caméras, files, occupation, incidents + prévisions |
| Analyser | Événements | journal filtrable + snapshots |
| Analyser | Rapports | export CSV/Excel/PDF |
| Configurer | **Zones & comptage** | éditeur visuel (sélecteur par site + preview) |
| Configurer | Règles & alertes | création de règles + notifications |
| Configurer | Caméras & site | CRUD, activation, géo, **sync HikCentral** |
| Configurer | Santé caméras | supervision « caméras traitées » + retry |
| Configurer | Carte | caméras géolocalisées |
| Configurer | Groupes | organisation du parc |
| Système | Utilisateurs & rôles, Audit, État système, Paramètres | administration |

---

## 5. API (principaux points d'entrée)

- **Auth** : `/auth/{register,login,refresh,logout,me,change-password,password-reset-*}`
- **Caméras** : `/cameras/` (CRUD, `/map-data`, `/{id}/active`)
- **Groupes** : `/groups/` (CRUD, membres)
- **Zones** : `/zones/` et `/zones/lines` (CRUD)
- **HikCentral** : `/hikcentral/{status,sync}`, `/hikcentral/stream-url`,
  `/hikcentral/cameras/{id}/retry`
- **Événements** : `/events/add`, `/events/`
- **Analytics** : `/analytics/{footfall,occupancy,queues,summary,insights,by-camera,incidents}`
- **Règles** : `/rules/` (CRUD)
- **Alertes** : `/alerts/` (liste paginée, stats, acknowledge, resolve, notify)
- **Dashboard** : `/dashboard/`
- **Admin** : `/users/`, `/audit/`, `/maintenance/`, `/sysInfo/`
- **Core (temps réel)** : Socket.IO `metadata`, `/api/gpu`, `/api/cameras/health`,
  `/api/cameras/{id}/preview`

---

## 6. Réglages clés (variables d'environnement)

| Variable | Rôle | Défaut |
|---|---|---|
| `PERSON_MODEL_PATH` | modèle YOLO (`yolo26n.pt` léger / `yolo26s.pt` précis) | `yolo26n.pt` |
| `PERSON_DETECTION_CONFIDENCE` | seuil de confiance | `0.4` |
| `PERSON_YOLO_HALF` | demi-précision GPU (FP16) | `true` |
| `BLUR_THRESHOLD` | gate anti-flou (0 = off ; abaisser pour le 360p) | `80` |
| `READ_FROM_MEDIAMTX` | lire le flux republié par MediaMTX | `true` |
| `CORE_API_KEY` | clé de service M2M backend↔core (vide = JWT) | *(vide)* |
| **`HIK_HOST` / `HIK_APP_KEY` / `HIK_APP_SECRET` / `HIK_USER_ID`** | connecteur HikCentral (AK/SK) | *(vide = off)* |
| `HIK_STREAM_TYPE` | flux ingéré (0 = main 1440p, 1 = sub 360p) | `1` |
| `HIK_TRANSCODE_ENCODER` | encodeur HEVC→H.264 (`libx264` / `h264_vaapi`…) | `libx264` |
| `HIK_SYNC_INTERVAL_MINUTES` | synchro périodique du catalogue (0 = off) | `15` |

---

## 7. Limites & feuille de route

**Livré depuis la dernière édition :**
- ✅ **Source HikCentral** (catalogue + activation paresseuse + preview + retry + synchro).
- ✅ **Analytique enrichie** : prévisions/baseline, heatmap, profil horaire, sites &
  caméras, incidents, deltas, export CSV.
- ✅ **Rebrand UI « Qwiper Sentinel »** + clé de service M2M + accès LAN.
- ✅ **Détection ajustable** (yolo26n/yolo26s, confiance, anti-flou par déploiement).

**Non encore implémenté / pistes :**
- **Alertes proactives de santé caméra** (offline agence → alerte auto). *Passif
  aujourd'hui (page santé + retry manuel).*
- **Configuration de détection PAR caméra** (confiance/modèle/flux 360p vs 1440p).
- **Pré-agrégation analytics** (`analytics_kpi` + jobs de fond) : aujourd'hui à la
  volée — à industrialiser pour la montée en charge (78+ caméras / 90 j).
- **Transcodage matériel** (VAAPI/QSV/NVENC) dans le chemin média pour scaler.
- **Rapports programmés** (email quotidien/hebdo) — l'export manuel existe.
- **Architecture edge** (détection en périphérie par agence, remontée des
  métadonnées seulement) — pour lever la contrainte de bande passante/liaison.

**Statut de validation :** le **pipeline temps réel** (détection → événements →
analytics → règles) est **validé de bout en bout avec de vraies détections** :
caméra HikCentral activée, transcodage H.264 confirmé (ffprobe), capture Core
`online`, événements réels alimentant l'analytique (affluence, attroupements,
alertes). Le levier de qualité restant est la **calibration du comptage** (précision/
rappel vs vérité terrain), dépendante de la résolution du flux et du modèle.

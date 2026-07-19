# OSIRION — Fonctionnalités du système

**Plateforme d'intelligence opérationnelle basée sur la vidéo — 100 % anonyme.**

> État au **2026-07-18**, branche `refactor/remove-lpr` (phases A→E de la refonte).
> Ce document décrit ce que le système **fait aujourd'hui**. La reconnaissance
> faciale et la lecture de plaques (LPR) ont été **entièrement retirées** : Osirion
> n'identifie personne, il analyse des **flux de personnes anonymes**.

---

## 1. Vue d'ensemble

Osirion transforme des caméras IP en **capteurs de données opérationnelles** :
combien de personnes entrent/sortent, combien sont présentes dans une zone,
quelle est la longueur et le temps d'attente d'une file, y a-t-il un attroupement,
une présence hors des heures autorisées… le tout **sans reconnaître les individus**
(aucune biométrie, aucune identité stockée).

Cas d'usage type : agences bancaires (files aux guichets), commerces
(fréquentation), hôpitaux, industrie, collectivités.

**Chaîne de valeur :**
```
Caméras RTSP → Détection de personnes (YOLO) → Tracking → Scene Model anonyme
   → Zones & lignes → Événements → Analytics (KPIs) → Règles → Alertes & notifications
```

---

## 2. Architecture (5 services)

| Service | Rôle | Techno |
|---|---|---|
| **db** | Persistance | PostgreSQL 15 |
| **backend** | API, auth, zones, règles, analytics, alertes | FastAPI (CPU) |
| **core** | Vision temps réel : détection + tracking + Event Engine | Flask + **GPU** |
| **mediamtx** | Transport vidéo (RTSP → WebRTC) | MediaMTX |
| **frontend** | Interface d'administration | Next.js 15 |

**Principe de sobriété :** une **seule** couche GPU (le Core, une passe YOLO par
frame). Tout le reste (événements, analytics, règles) est du CPU léger, hors du
chemin critique vidéo. La vidéo affichée passe par WebRTC (décodage natif du
navigateur), séparée des métadonnées d'analyse (JSON via Socket.IO).

---

## 3. Fonctionnalités par domaine

### 3.1 Acquisition & streaming vidéo
- **Multi-caméras RTSP** (caméras IP / NVR).
- **Ajout/retrait de caméras à chaud** : le Core réconcilie périodiquement la
  liste avec le backend (≈15 s) — pas de redémarrage.
- **Reconnexion RTSP automatique** illimitée (backoff exponentiel, plafonné) :
  une caméra qui retombe se reconnecte seule.
- **MediaMTX** : une **seule** connexion à la caméra physique, republiée en
  **WebRTC** pour le navigateur (décodage natif, faible latence) et lue par le
  Core pour l'analyse. Chemins MediaMTX créés/supprimés dynamiquement par caméra.
- **Filtre anti-flou** : une frame trop floue est sautée (pas d'inférence inutile).

### 3.2 Vision Engine anonyme (le cœur GPU)
- **Détection de personnes** par YOLO (modèle **yolo26n** par défaut : NMS-free,
  edge-optimisé, ~5 Mo, FP16 sur GPU). Classe COCO « person » uniquement.
- **Tracking multi-objets OC-SORT** : chaque personne reçoit un **identifiant de
  suivi anonyme** (`track_id`) persistant entre les frames — jamais une identité.
- **Scene Model** produit à chaque frame et diffusé en JSON :
  `{ camera_id, width, height, detections: [{ track_id, bbox, foot (point au sol),
  velocity (vitesse/direction), zones[] }] }`.
- **Overlay temps réel** dans le navigateur : boîtes anonymes dessinées sur la
  vidéo (canvas), alignées automatiquement quelle que soit la résolution.
- **Dégradation gracieuse** : si le modèle ne charge pas, le flux vidéo continue.

### 3.3 Zones & lignes de comptage (configurables)
- **Éditeur visuel** (`Zones & comptage`) : on choisit une caméra, on voit son
  flux live, et on **dessine** par-dessus :
  - **Zones** (polygones) de type *occupation*, *file d'attente*, *attroupement*
    ou *générique*, avec un **seuil** optionnel (déclenchement d'attroupement) ;
  - **Lignes de comptage** (segment) avec un **sens « entrée »** (in/out).
- **Coordonnées normalisées** [0,1] → un tracé reste valable même si la résolution
  change.

### 3.4 Event Engine (détection d'événements métier)
Calculé côté Core (CPU léger) à partir du Scene Model, émis en **fire-and-forget**
(le thread caméra n'est jamais bloqué par le réseau) :
- **`ZONE_OCCUPANCY_CHANGED`** — le nombre de personnes dans une zone change
  (throttlé). Un **snapshot** est joint à la transition 0→occupé (utile intrusion).
- **`CROWD_DETECTED`** — occupation ≥ seuil de la zone, **soutenue N secondes**
  (anti-faux-positif) + snapshot → *attroupement*.
- **`LINE_CROSSED`** — une personne franchit une ligne, avec le **sens** (entrée /
  sortie) → *comptage*.
- **`ZONE_DWELL`** — **temps de présence** d'une personne à sa sortie d'une zone
  → *temps d'attente* d'une file, temps passé par zone.

### 3.5 Analytics (indicateurs opérationnels)
Page **Analytics** + endpoints, calculés **à la volée** depuis les événements
(toujours frais) :
- **Fréquentation** : entrées / sorties / net **par jour** (graphe 7 jours) +
  estimation des présents.
- **Files d'attente** : longueur actuelle + **temps d'attente moyen / max** par file.
- **Occupation par zone** : moyenne / max / actuel.
- **Résumé du jour** : entrées, sorties, présents estimés, occupation, attroupements,
  temps d'attente moyen.

### 3.6 Moteur de règles & alertes (le système « agit »)
- **Règles configurables** (page `Règles & alertes`) : *SI un événement satisfait
  des conditions PENDANT une plage horaire ALORS créer une alerte (+ notifier)*.
  - **Déclencheur** : occupation, attroupement, franchissement, temps de présence.
  - **Conditions** : occupation min, temps d'attente min, sens.
  - **Plage horaire armée** : jours + heures, **gère le passage minuit** (ex.
    22h→6h) — base de l'**intrusion horaire**.
  - **Restriction à une zone** optionnelle.
- **Cas d'usage couverts** :
  - **Intrusion horaire** : présence dans une zone armée hors des heures → alerte
    + **photo** + notification.
  - **Attroupement / saturation guichet** : occupation ou file au-delà d'un seuil.
- **Alertes** : centre d'alertes avec **workflow** *nouveau → acquitté → résolu*.
- **Notifications** : **email (SMTP)** et **webhook** — automatiques (par règle) ou
  manuelles (bouton sur une alerte).
- **Temps réel** : toast + son dans l'interface dès qu'une alerte est créée.

### 3.7 Caméras, groupes & cartographie
- **CRUD caméras** : nom, URL RTSP (**chiffrée** au repos), localisation,
  activation/désactivation, géo-coordonnées (lat/lon + cap boussole).
- **Groupes de caméras** : organisation logique du parc.
- **Carte** (OpenStreetMap/Leaflet) : caméras géolocalisées + **cône de champ de
  vision**.
- **Santé des caméras** : FPS, état (online / connecting / offline / stalled),
  uptime — rafraîchi en temps réel.

### 3.8 Dashboard, événements & rapports
- **Dashboard** : KPIs (caméras actives, événements, alertes), graphe d'activité,
  aperçus live.
- **Journal d'événements** : filtrable par type / caméra, avec snapshots et
  contexte (zone, occupation, sens).
- **Rapports** : tableau filtrable (période, type) + **export CSV / Excel / PDF**
  (déclenché manuellement).

### 3.9 Sécurité & administration
- **Authentification JWT** (access 30 min + refresh 7 j, rotation).
- **Rôles (RBAC)** : `admin`, `user`, `viewer` — appliqués backend **et** frontend.
- **Gestion des utilisateurs** (admin) : création, rôles, activation.
- **Journal d'audit** (admin) : actions tracées.
- **Maintenance** (admin) : purge des anciens événements/snapshots.
- **Monitoring système** (admin) : CPU / RAM / disque, et **GPU** (utilisation,
  mémoire, température).
- **Durcissements** : rate-limiting, verrouillage de compte, chiffrement Fernet
  des URL RTSP, CORS strict en production.

### 3.10 Confidentialité / RGPD
- **Aucune donnée biométrique**, aucune reconnaissance faciale, aucune plaque.
- Les personnes sont des **objets anonymes** suivis le temps de leur passage.
- Argument de conformité fort (banques, hôpitaux) : analyse opérationnelle **sans
  fichage nominatif**.

---

## 4. Interface (pages d'administration)

| Page | Fonction |
|---|---|
| Tableau de bord | KPIs + activité + aperçus |
| Caméras | CRUD, activation, géo |
| Santé caméras | supervision temps réel (FPS/état) |
| Groupes de caméras | organisation du parc |
| **Zones & comptage** | éditeur visuel de zones/lignes |
| **Analytics** | fréquentation, files, occupation |
| **Règles & alertes** | création de règles + notifications |
| Alertes | centre d'alertes (workflow + notif) |
| Live | grille de flux WebRTC + overlay |
| Carte | caméras géolocalisées |
| Événements | journal filtrable + snapshots |
| Rapports | export CSV/Excel/PDF |
| Utilisateurs & rôles | administration des comptes |
| Audit | journal des actions |
| État système | CPU/RAM/disque/GPU |
| Paramètres | réglages généraux |

---

## 5. API (principaux points d'entrée)

- **Auth** : `/auth/{register,login,refresh,logout,me,change-password,password-reset-*}`
- **Caméras** : `/cameras/` (CRUD, `/map-data`, `/{id}/active`)
- **Groupes** : `/groups/` (CRUD, membres)
- **Zones** : `/zones/` et `/zones/lines` (CRUD)
- **Événements** : `/events/add`, `/events/`
- **Analytics** : `/analytics/{footfall,occupancy,queues,summary}`
- **Règles** : `/rules/` (CRUD)
- **Alertes** : `/alerts/` (liste, stats, acknowledge, resolve, notify)
- **Dashboard** : `/dashboard/`
- **Admin** : `/users/`, `/audit/`, `/maintenance/`, `/sysInfo/`
- **Core (temps réel)** : Socket.IO `metadata`, `/api/gpu`, `/api/cameras/health`

---

## 6. Réglages clés (variables d'environnement)

| Variable | Rôle | Défaut |
|---|---|---|
| `PERSON_MODEL_PATH` | modèle YOLO de détection | `yolo26n.pt` |
| `PERSON_DETECTION_CONFIDENCE` | seuil de confiance | `0.4` |
| `PERSON_YOLO_HALF` | demi-précision GPU (FP16) | `true` |
| `BLUR_THRESHOLD` | gate anti-flou (0 = off) | `80` |
| `CROWD_MIN_SECONDS` | durée avant alerte attroupement | `3` |
| `OCCUPANCY_EMIT_INTERVAL` | throttle occupation | `2` |
| `DWELL_MIN_SECONDS` | temps de présence minimal émis | `1` |
| `ZONES_REFRESH_SECONDS` | rafraîchissement zones (Core) | `30` |
| `RULE_TZ_OFFSET_HOURS` | décalage horaire des plages de règles | `0` |
| `READ_FROM_MEDIAMTX` | lire le flux republié par MediaMTX | `true` |

---

## 7. Limites & feuille de route (non encore livré)

**Volontairement non implémenté à ce stade :**
- **Reporting automatique planifié** (rapports quotidiens/hebdo/mensuels envoyés
  par email) — l'export manuel existe, la planification non. *(Phase F)*
- **Dashboard temps réel enrichi + heatmap de fréquentation.** *(Phase F)*
- **Multi-tenant, SDK, système de plugins, marketplace.** *(Phase G — post-clients)*
- **Pré-agrégation analytics** (`analytics_kpi` + jobs de fond) : aujourd'hui les
  analytics sont calculés à la volée (adapté à l'échelle actuelle).
- **Inférence batchée multi-caméras** : levier de performance pour aller vers
  20–30+ caméras sur un même GPU (passe dédiée à mesurer avant/après).

**Statut de validation :** le code des phases A→E est vérifié par compilation
(Python) et build (frontend). Le **pipeline temps réel** (détection → événements →
analytics → règles) a démarré correctement (modèle YOLO chargé sur GPU) mais n'a
**pas encore été validé de bout en bout avec de vraies détections** faute de flux
caméra stable pendant les tests. Recommandation : rebuild de l'image `core` +
source vidéo de test pour une validation complète.

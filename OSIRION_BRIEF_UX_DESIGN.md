# OSIRION — Brief UX/UI pour refonte du frontend

> **À l'attention du designer (Claude Design).** Ce document est **auto-suffisant** :
> tu n'as pas besoin d'accéder au code. Il décrit le produit, les utilisateurs,
> leurs objectifs, **chaque écran avec les données exactes disponibles** (au niveau
> des champs, avec exemples JSON réels), les comportements temps réel et les
> contraintes techniques. **Tu es libre de repenser entièrement l'architecture de
> l'information, les parcours et les visualisations.** Si tu proposes des données
> supplémentaires (nouveaux graphes, KPIs, vues), indique-les : on saura les produire
> côté backend (§10 liste déjà ce qui est facilement calculable).
>
> Objectif : l'expérience actuelle est à revoir. On veut une interface **claire,
> fluide, sobre et « opérationnelle »** (un cockpit, pas un back-office).
> ⚠ Lire aussi ANNEXE_REFERENCE_VISUELLE_HIKCENTRAL.md
---

## 1. Le produit en une page

**Osirion** transforme des caméras de vidéosurveillance en **capteurs de données
opérationnelles anonymes**. Il ne reconnaît **personne** (aucune biométrie, aucun
visage, aucune plaque) : il détecte et suit des **personnes anonymes** pour mesurer
des flux et déclencher des alertes.

Ce qu'il produit :
- **Comptage** entrées/sorties (fréquentation).
- **Occupation** des zones en temps réel.
- **Files d'attente** : longueur + temps d'attente.
- **Attroupement** (densité au-delà d'un seuil).
- **Intrusion horaire** (présence hors des heures autorisées) + photo.
- **Alertes & notifications** (email/webhook) sur règles configurables.

**Clients cibles** : agences bancaires (files aux guichets), retail (fréquentation),
hôpitaux, industrie, collectivités. **Différenciateur clé : 100 % anonyme** → argument
RGPD fort (pas de fichage nominatif).

**Déploiement** : application web auto-hébergée (on-premise), consultée sur poste de
bureau surtout, parfois tablette. Multilingue non requis pour l'instant (**FR**).

---

## 2. Personas & « jobs-to-be-done »

| Persona | Rôle appli | Ce qu'il veut faire |
|---|---|---|
| **Opérateur / superviseur** | `viewer` / `user` | Surveiller en **temps réel** (murs de caméras, occupation, files) ; **réagir aux alertes** (voir, acquitter, résoudre) ; repérer une file qui déborde ou une intrusion. |
| **Manager opérationnel** | `user` / `admin` | **Analyser** : fréquentation par jour/heure, temps d'attente, occupation ; comparer des périodes ; **configurer** zones & règles pour son site. |
| **Administrateur** | `admin` | Gérer **caméras**, **utilisateurs**, **système** (santé, GPU, audit, purge). |

**Insight de conception** : aujourd'hui l'app est structurée comme un *back-office de
surveillance* (une page par entité : caméras, événements, alertes…). Pour un **produit
d'intelligence opérationnelle**, on gagnerait sans doute à séparer 3 intentions :
**SURVEILLER** (temps réel) · **ANALYSER** (tendances/insights) · **CONFIGURER**
(zones, règles, caméras, admin). Libre à toi de proposer cette IA ou une meilleure.

---

## 3. État actuel & douleurs UX (à corriger)

- L'app a grandi de façon organique → **navigation à plat** (~16 entrées de menu
  hétérogènes), pas de hiérarchie « surveiller / analyser / configurer ».
- **Pas de vrai cockpit temps réel** : l'occupation, les files et les alertes live
  ne sont pas réunies en une vue de supervision unique.
- Des **tables denses** d'admin (événements, rapports, alertes) peu lisibles.
- **Graphiques minimalistes** faits main (barres CSS) — pas de langage visuel data cohérent.
- Le **live vidéo** (mur de caméras) et l'**analyse** ne communiquent pas (on ne voit
  pas les zones/compteurs superposés à la vidéo dans un contexte opérationnel).
- Reste des vestiges d'ex-fonctionnalités « surveillance » (vocabulaire « blacklist »,
  etc.) à évacuer au profit d'un langage **opérationnel & anonyme**.

---

## 4. Objectifs & principes de design

1. **Cockpit opérationnel** : la page d'accueil doit répondre en 3 secondes à « tout
   va bien ? » (occupation, files, alertes actives, caméras en ligne).
2. **Sobre & fluide** : dense en information mais calme ; pas de surcharge ; hiérarchie
   visuelle forte ; temps de compréhension minimal.
3. **Temps réel lisible** : distinguer clairement « live » (qui bouge) et « historique ».
4. **Anonyme par design** : jamais d'identité ; le vocabulaire parle de « personnes »,
   « flux », « occupation » — pas d'individus nommés.
5. **Thème clair ET sombre** (les deux existent déjà, à conserver).
6. **Accessibilité** : contrastes, tailles, états focus.

---

## 5. Contraintes techniques (à respecter)

- **Stack** : Next.js 15 (App Router) + **React 19** + **Tailwind CSS**. Icônes :
  `lucide-react` (et SVG inline). **Pas de librairie de charts** aujourd'hui (graphes
  custom SVG/CSS) — tu peux en proposer une (ex. Recharts) ou rester en SVG maison ;
  précise ton choix.
- **Thème** clair/sombre déjà géré (variables CSS + classes `dark:`).
- **Vidéo live** : élément HTML `<video>` alimenté en **WebRTC** (flux natif de la
  caméra via un relais). Par-dessus, un **`<canvas>` transparent** dessine les boîtes
  de détection (overlay). Ton design doit prévoir ce couple vidéo+overlay et des
  grilles de caméras (1/2/3/4 colonnes, plein écran).
- **Données** : tout vient d'une API REST (JSON) + un flux **Socket.IO** pour le temps
  réel (le « Scene Model » par frame). Détails §8–9.
- Cible écran : **desktop d'abord** (1280–1920), responsive tablette souhaitable.

---

## 6. Rôles & permissions (ce que chaque rôle peut voir/faire)

- `viewer` : **lecture** (dashboards, live, événements, alertes, analytics). Peut
  acquitter/résoudre des alertes selon config.
- `user` : viewer **+ écriture métier** (caméras, groupes, zones, règles, notifier).
- `admin` : tout **+ utilisateurs, audit, maintenance, système**.

Le design doit gérer l'**affichage conditionnel** (masquer/désactiver les actions
non permises) et un état « accès refusé ».

---

## 7. Architecture de l'information ACTUELLE (à repenser)

Menu latéral actuel (à plat) : Tableau de bord · Caméras · Santé caméras · Groupes ·
**Zones & comptage** · **Analytics** · **Règles & alertes** · Alertes · Live · Carte ·
Événements · Rapports · Utilisateurs · Audit · État système · Paramètres.

→ **Propose une meilleure organisation** (regroupements, hiérarchie, page d'accueil
« cockpit », navigation contextualisée par site/caméra, etc.).

---

## 8. Inventaire détaillé des écrans (données réelles à afficher)

Pour chaque écran : **but**, **données disponibles** (champs), **actions**, **états**
(vide / chargement / erreur), **temps réel**.

### 8.1 Cockpit / Tableau de bord (accueil)
- **But** : vue de supervision « tout-en-un ».
- **Données dispo** (endpoint `/analytics/summary`) :
  `entries_today, exits_today, present_now_estimate, current_occupancy,
  crowd_alerts_today, avg_wait_s`.
  + `/dashboard` : `counts{cameras, events_total, alerts_total, alerts_new}`,
  `events_by_type{...}`, `events_by_day[{date, count}]`.
  + occupation par zone (`/analytics/occupancy` → `zones[]`), files (`/analytics/queues`),
  alertes récentes (`/alerts?status=new`), santé caméras (état online/offline).
- **États** : beaucoup de compteurs peuvent être à 0 (pas encore de données) → prévoir
  des **états vides pédagogiques** (« dessinez une zone pour commencer »).
- **Temps réel** : les KPIs et alertes se rafraîchissent (polling ~10 s).

### 8.2 Live (mur de caméras)
- **But** : voir les flux en direct avec overlay des personnes détectées.
- **Données** : liste des caméras actives + par caméra un flux **WebRTC** + le
  **Scene Model** temps réel (Socket.IO, §9) → boîtes anonymes, latence, cadence.
- **Actions** : choisir la grille (2/3/4 col.), plein écran, sélectionner une caméra.
- **Idée design** : superposer **zones dessinées** + **compteurs live** (occupation de
  la zone, longueur de file) directement sur la vidéo.

### 8.3 Zones & comptage (éditeur visuel)
- **But** : dessiner des **zones** (polygones) et **lignes de comptage** sur le flux
  d'une caméra.
- **Données** (`/zones?camera_id=`, `/zones/lines?camera_id=`) :
  Zone `{id, camera_id, name, kind (occupancy|queue|crowd|generic), polygon:[[x,y]…]
  (normalisé 0-1), color, threshold, is_active}` ;
  Ligne `{id, camera_id, name, point_a:[x,y], point_b:[x,y], in_direction (positive|
  negative), is_active}`.
- **Interaction** : outil « zone » (clics → polygone ≥3 pts), outil « ligne » (2 pts),
  nom, type, seuil ; liste + suppression. **Point délicat UX** : rendre le dessin sur
  vidéo intuitif (annuler point, fermer polygone, poser la flèche de sens d'une ligne).

### 8.4 Analytics (fréquentation, files, occupation)
- **But** : analyser les flux.
- **Données** :
  - `/analytics/footfall?days=7` → `{total_entries, total_exits, present_estimate,
    series:[{date, entries, exits, net}]}` (comptage par jour).
  - `/analytics/queues` → `queues:[{zone_id, name, camera_id, length, wait_avg_s,
    wait_max_s, samples}]`.
  - `/analytics/occupancy` → `zones:[{zone_id, zone_name, count, t}]` ; avec `?zone_id=`
    → `{series:[{t, count}], avg, max, current}` (courbe d'occupation).
- **Opportunité** : c'est LE terrain de jeu data-viz (courbes, comparaisons, heatmaps —
  cf. §10 pour ce qu'on peut ajouter : par heure, distributions, tendances…).

### 8.5 Règles & alertes (configuration des décisions)
- **But** : créer des règles « SI événement (conditions) PENDANT plage horaire ALORS
  alerte + notif ».
- **Données** (`/rules`) : `{id, name, trigger (ZONE_OCCUPANCY_CHANGED|CROWD_DETECTED|
  LINE_CROSSED|ZONE_DWELL), zone_id, conditions{min_count|min_wait_s|direction},
  schedule{days:[0-6], from:"HH:MM", to:"HH:MM"}, kind (intrusion|crowd|queue|custom),
  notify_channels:["email","webhook"], is_active}`.
- **Point délicat UX** : rendre la construction d'une règle **lisible pour un
  non-technicien** (ex. un assistant « intrusion nuit » pré-rempli ; sélecteur de
  jours/heures clair ; aperçu en langage naturel de la règle).

### 8.6 Alertes (centre d'alertes)
- **But** : traiter les alertes déclenchées par les règles.
- **Données** (`/alerts?status=`) : `{id, kind, label, reason, camera_id, camera_name,
  snapshot_url, status (new|acknowledged|resolved), acknowledged_at, acknowledged_by,
  notified_at, notified_channel, created_at}`. + `/alerts/stats`.
- **Actions** : acquitter, résoudre, **notifier** (email/webhook), filtrer par statut.
- **Temps réel** : nouvelles alertes → **toast + son** (déjà en place, à re-designer).
- **Idée** : timeline d'alertes + **vignette snapshot** + workflow visuel (new→ack→resolved).

### 8.7 Caméras / Groupes / Carte / Santé
- **Caméras** (`/cameras`) : `{id, cam_name, rtsp_url, location, is_active, latitude,
  longitude, bearing (0-360°), group_ids[], created_at}`. Actions : CRUD, activer.
- **Groupes** (`/groups`) : `{id, name, description, camera_ids[], camera_count}`.
- **Carte** (`/cameras/map-data`) : `{id, name, latitude, longitude, bearing}` →
  marqueurs + **cône de champ de vision** (Leaflet/OpenStreetMap).
- **Santé caméras** (Core `/api/cameras/health`) : `{id, name, location, state
  (online|connecting|offline|stalled|stopped), fps, uptime, last_frame_age_s,
  reconnection_attempts, threads_alive}`. Temps réel (polling 2 s).

### 8.8 Événements & Rapports
- **Événements** (`/events`) : `{id, camera_id, camera_nom, camera_location, event_type,
  confidence, snapshot_url, meta{…}, timestamp}`. Filtres type/caméra ; lightbox snapshot.
  Types : `ENTRY, EXIT, DETECTION, ZONE_OCCUPANCY_CHANGED, CROWD_DETECTED, LINE_CROSSED,
  ZONE_DWELL`. `meta` porte `{zone_id, zone_name, kind, count, line_id, line_name,
  direction, dwell_s}` selon le type.
- **Rapports** : même source événements + **export CSV/Excel/PDF** (manuel), filtres période.

### 8.9 Administration (admin)
- **Utilisateurs** (`/users`) : `{id, fullName, email, role (admin|user|viewer),
  is_active, is_verified, last_login, created_at}`. CRUD + rôles.
- **Audit** (`/audit`) : `{user_email, action, target_type, target_id, detail,
  ip_address, created_at}`.
- **État système** : CPU/RAM/disque + **GPU** (`/api/gpu` : `{available, gpus:[{name,
  utilization_percent, memory_used_mb, memory_total_mb, temperature_c}]}`).
- **Maintenance** : purge des anciens événements/snapshots.
- **Paramètres** : réglages généraux (nom du site, timeout de session…).

---

## 9. Temps réel & streaming (spécificités à designer)

1. **Vidéo** : chaque caméra = un `<video>` WebRTC (flux natif). Latence faible.
2. **Overlay « Scene Model »** : un flux **Socket.IO** pousse, par frame, un JSON :
   ```json
   {
     "camera_id": 13, "width": 1280, "height": 720,
     "detections": [
       { "type": "person", "track_id": 42,
         "bbox": [120, 200, 210, 460],
         "foot": [165, 460], "velocity": [3.2, -1.1],
         "zones": [1] }
     ]
   }
   ```
   → boîtes anonymes dessinées sur un `<canvas>` aligné à la vidéo. Le design peut
   exploiter `zones` (surligner une personne dans une zone), `velocity` (direction),
   `foot` (point au sol, pour heatmap/position).
3. **Alertes temps réel** : polling `/api/alerts?status=new` (~10 s) → toast + son.
4. **Santé caméras / GPU** : polling ~2 s.

---

## 10. Données qu'on peut PRODUIRE si le design en a besoin

On calcule aujourd'hui à la volée depuis un journal d'événements riche. Sont
**facilement ajoutables** (dis-nous ce qui sert ta maquette) :
- **Fréquentation par HEURE** (pas seulement par jour) — courbe intra-journalière,
  heures de pointe.
- **Courbe d'occupation dans le temps** par zone (déjà exposable en série).
- **Distribution des temps d'attente** (histogramme) par file.
- **Comparaison période à période** (aujourd'hui vs même jour la semaine dernière).
- **Heatmap de fréquentation** : accumulation des **points au sol** sur une grille
  (données `foot` déjà présentes dans le Scene Model) — vue « zones chaudes ».
- **Taux d'occupation vs capacité** si on ajoute une **capacité** par zone (champ à créer).
- **Matrice de flux** entrées/sorties par ligne / par heure.
- **Vignettes snapshot** des dernières alertes / des derniers événements.
- **Statut agrégé du site** (score « tout va bien / attention / critique »).
- **Horaires d'ouverture** par site (pour contextualiser les KPIs) — champ à créer.

> En clair : si ta proposition exige une donnée qui n'existe pas encore, **liste-la**,
> on la produit. Ne te bride pas sur la disponibilité des données.

---

## 11. Livrables attendus du designer

1. **Architecture de l'information** repensée (regroupements, navigation, page d'accueil).
2. **Maquettes** des écrans clés — priorité :
   - **Cockpit temps réel** (occupation + files + alertes + caméras, vue « site »),
   - **Analytics** (fréquentation, files, occupation — data-viz),
   - **Live** (mur de caméras + overlay + compteurs de zone),
   - **Éditeur de zones** (dessin sur vidéo, UX du tracé),
   - **Création de règle** (compréhensible par un non-technicien),
   - **Centre d'alertes** (workflow + snapshots + temps réel).
3. **Système visuel** : palette (clair/sombre), typographie, composants (KPI card,
   graphes, tables, badges d'état, toasts d'alerte), langage data-viz cohérent.
4. **États** : vide / chargement / erreur / accès refusé, pour chaque écran.
5. **Micro-interactions** utiles au temps réel (mise à jour live, alertes entrantes).

---

### Annexe — glossaire métier
- **Zone** : polygone sur l'image d'une caméra (occupation / file / attroupement).
- **Ligne de comptage** : segment qu'on compte quand une personne le franchit (sens in/out).
- **Occupation** : nombre de personnes présentes dans une zone à un instant t.
- **Temps de présence (dwell)** : durée passée par une personne dans une zone (= temps
  d'attente pour une file).
- **Attroupement** : occupation ≥ seuil pendant une durée.
- **Règle** : condition (+ plage horaire) qui déclenche une **alerte** + notification.
- **Track (anonyme)** : une personne suivie le temps de son passage (identifiant
  éphémère, aucune identité).

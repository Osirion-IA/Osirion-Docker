# Architecture de streaming Osirion — Évolution (Phases 1 & 2)

> **Document pour le mémoire de fin d'études.** Il décrit le passage de l'architecture
> initiale « tout-Socket.IO / JPEG » à une **architecture VMS professionnelle** :
> **vidéo en WebRTC** (décodée nativement par le navigateur) + **métadonnées JSON
> en Socket.IO** (bounding boxes dessinées côté client).
>
> ⚠️ **Ce document complète et CORRIGE** `ANALYSE_TECHNIQUE_OSIRION.md`, dont la
> partie « streaming » décrit l'ancienne architecture. Voir le **§8 — Mises à jour à
> apporter au mémoire** pour la liste exacte des passages à corriger.
>
> Tout ce qui suit est 🟢 (lu/implémenté directement dans le code du dépôt).

---

## Table des matières
1. [Résumé exécutif (avant / après)](#1-résumé-exécutif)
2. [Pourquoi changer ? Les goulots d'étranglement](#2-pourquoi-changer)
3. [Phase 1 — Optimisation du pipeline](#3-phase-1)
4. [Phase 2 — Architecture VMS (WebRTC + métadonnées)](#4-phase-2)
5. [Ce qui a changé, fichier par fichier](#5-fichier-par-fichier)
6. [Protocoles : qui utilise quoi ?](#6-protocoles)
7. [Configuration & variables d'environnement](#7-configuration)
8. [Mises à jour à apporter au mémoire](#8-mises-à-jour-mémoire)
9. [Bénéfices mesurés](#9-bénéfices)
10. [Limites & pistes d'amélioration](#10-limites)

---

## 1. Résumé exécutif

| Aspect | AVANT (architecture initiale) | APRÈS (Phases 1 & 2) |
|---|---|---|
| **Transport vidéo** | Frames JPEG encodées par le Core, poussées en Socket.IO (`frame`) à ~30 FPS | **WebRTC (WHEP)** servi par **MediaMTX**, décodage **natif/accéléré** par le navigateur |
| **Annotations (boxes)** | Dessinées par OpenCV **dans l'image** côté Core, incrustées dans le JPEG | **JSON** envoyé en Socket.IO (`metadata`), dessiné sur un **`<canvas>` superposé** côté client |
| **Rôle du Core** | Vision **+ encodage vidéo + dessin** | **Vision uniquement** (détection/tracking/reconnaissance) → publie des métadonnées |
| **Connexion caméra** | 2 connexions RTSP (Core + … ) | **1 seule** connexion (MediaMTX), partagée IA + vidéo |
| **Nb de services Docker** | **4** (db, backend, core, frontend) | **5** (+ **mediamtx**) |
| **Encodage JPEG côté Core** | `cv2.imencode` à chaque frame | **Supprimé** |
| **Socket.IO** | Transport **vidéo** | Transport **métadonnées** uniquement (toujours présent !) |

> 🔑 **Point à retenir pour le mémoire** : on n'a **pas supprimé le WebSocket**. Socket.IO
> (Flask-SocketIO) reste utilisé — mais **uniquement pour les métadonnées JSON** (les
> bounding boxes), plus pour la vidéo. La **vidéo** est passée en **WebRTC**.

---

## 2. Pourquoi changer ?

L'architecture initiale faisait tout transiter par le Core et par Socket.IO :

1. **CPU du Core saturé** — pour chaque frame de chaque caméra, le Core devait :
   `cv2.imencode('.jpg', …)` (encodage JPEG), dessiner les boîtes (`cv2.rectangle`,
   `cv2.putText`), et auparavant `frame.copy()` + `cv2.addWeighted()` (fonds
   semi-transparents) → **plusieurs memcpy plein écran par track et par frame**.
2. **Bande passante & latence** — JPEG (puis base64) poussé à 30 FPS sur le réseau ;
   le base64 ajoute +33 % de volume et un coût de décodage JS.
3. **Pipeline figé par le réseau** — la boucle vidéo attendait les réponses HTTP du
   backend (recherche FAISS + création d'événement) via `loop.run_until_complete(...)`.
4. **Pas d'accélération matérielle** — le navigateur ré-affichait des JPEG dans un
   `<canvas>` au lieu d'utiliser son décodeur vidéo natif (H.264/GPU).

---

## 3. Phase 1 — Optimisation du pipeline (sans changer l'architecture Socket.IO)

Trois « quick wins » appliqués **avant** la bascule WebRTC. Les points (b) et (c)
**restent valables** dans l'architecture finale ; le point (a) a ensuite été
**rendu obsolète** par la Phase 2 (plus de frames du tout).

| # | Optimisation | Détail | Statut final |
|---|---|---|---|
| (a) | **Frames binaires** | base64 → octets JPEG bruts (`bytes`) sur Socket.IO ; rendu via `Blob` + `URL.createObjectURL` | Remplacé par WebRTC en Phase 2 |
| (b) | **Dessin opaque** | suppression de `frame.copy()` + `cv2.addWeighted()` (memcpy plein écran par track) ; rectangle de fond **opaque** direct | Le **dessin** a ensuite migré côté client (Phase 2), mais le principe « pas de memcpy » reste |
| (c) | **Reconnaissance fire-and-forget** | la recherche FAISS + l'envoi d'événement quittent le thread vidéo via un **worker dédié** (file `queue.Queue` + boucle asyncio propre) ; la boucle vidéo ne bloque **jamais** sur le réseau | **Toujours actif** (cf. `tracking_processor.py`) |

> Référence dans le code : `core/tracking_processor.py` (worker `_recognition_loop`,
> `_submit_recognition`, `_drain_recognition_results`), calqué sur le worker déjà
> présent dans `core/plate_processor.py` (`_lookup_loop`).

---

## 4. Phase 2 — Architecture VMS (WebRTC + métadonnées JSON)

### 4.1 Vue d'ensemble

```
                         ┌──────────────────────────────────────────────┐
   Caméra IP (HIKVISION) │                  MediaMTX                     │
   RTSP H.264 + G.711    │  (proxy média, conteneur osirion-mediamtx)   │
        192.168.1.64 ────┼──► RTSP source (TCP, 1 seule connexion) ──┐  │
                         │                                            │  │
                         │   ┌── RTSP republié (TCP) ────────────────┘  │
                         │   │   :8554/cam3                              │
                         │   │                                          │
                         │   └── WebRTC / WHEP  :8889 ──────────────┐   │
                         └──────────────────────────────────────────┼───┘
                                                                     │
        ┌────────────────────────────────┐                          │
        │  Core (osirion-core, Flask)     │                          │
        │  lit rtsp://mediamtx:8554/cam3  │◄─────────────────────────┤ (vidéo)
        │  → détection / tracking / reco  │                          │
        │  → publie des MÉTADONNÉES JSON  │                          ▼
        │     (bounding boxes)            │                  ┌────────────────┐
        └───────────────┬─────────────────┘                  │   Navigateur   │
                        │ Socket.IO  event 'metadata'         │  (Next.js)     │
                        └────────────────────────────────────►│  <video> WebRTC│
                                                              │  + <canvas>    │
                                                              │    overlay     │
                                                              └────────────────┘
```

### 4.2 Composants

- **MediaMTX** (`bluenviron/mediamtx:latest`, service `mediamtx`) — proxy média :
  ingère le RTSP de la caméra (à la demande) et le **republie** en **RTSP** (pour le
  Core) et en **WebRTC/WHEP** (pour le navigateur). Configuration : `mediamtx.yml`.
- **Core** (`osirion-core`) — ne fait **plus** de vidéo : il lit le flux, exécute
  l'IA (SCRFD + ArcFace + ByteTrack + LPR), et **publie un payload JSON** de
  détections via Socket.IO. Aucune image n'est encodée ni envoyée au frontend.
- **Frontend** (`osirion-frontend`, Next.js) — affiche la vidéo via un **client WHEP
  natif** dans une balise `<video>`, et **dessine les boîtes** sur un `<canvas>`
  transparent superposé, à chaque événement `metadata`.

### 4.3 Flux de données détaillé

1. Le navigateur ouvre `/Osirion/admin/live` → composant `CameraStream.js`.
2. **Vidéo** : le composant fait une négociation **WHEP** (offre/réponse SDP, non-trickle)
   vers `http://localhost:8889/cam3/whep`. MediaMTX, à la demande, se connecte à la
   caméra (RTSP/TCP) et renvoie le flux H.264 en WebRTC. Le `<video>` l'affiche.
3. **Overlay** : le composant ouvre une connexion **Socket.IO** vers le Core (`:5000`),
   émet `start_stream {camera_id}`, puis reçoit en continu l'événement **`metadata`** :
   ```json
   {
     "camera_id": 3,
     "width": 640,
     "height": 480,
     "detections": [
       {"type":"face",  "track_id": 12, "bbox":[x1,y1,x2,y2], "label":"Nom 87%", "recognized": true},
       {"type":"plate", "track_id": 4,  "bbox":[x1,y1,x2,y2], "label":"AB-123-CD", "alert": false, "known": true}
     ]
   }
   ```
   À chaque payload : le canvas est **effacé** puis les boîtes + libellés sont
   **redessinés** côté client (couleurs : vert=reconnu, rouge=inconnu/blacklist,
   cyan=plaque connue, ambre=plaque détectée).
4. Le Core, en parallèle, lit le **même** flux depuis MediaMTX (`rtsp://mediamtx:8554/cam3`)
   pour son inférence — **sans 2ᵉ connexion à la caméra physique**.

### 4.4 Le point crucial : connexion caméra **unique** (option `READ_FROM_MEDIAMTX`)

Sans cette option, **deux** processus ouvriraient le flux de la caméra (le Core ET
MediaMTX) → double charge réseau, et la caméra HIKVISION supportait mal 2 flux
principaux simultanés (pertes RTP massives). Avec `READ_FROM_MEDIAMTX=true` :

- **MediaMTX** est le **seul** à se connecter à la caméra physique (en **TCP**).
- Le **Core** lit le flux **republié** par MediaMTX sur le réseau interne Docker
  (`rtsp://mediamtx:8554/cam3`, TCP, sans perte).
- Le **navigateur** lit le même flux en WebRTC.
- → **1 connexion caméra**, partagée entre l'IA et la vidéo. C'est le schéma
  canonique d'un **VMS** (Video Management System).

### 4.5 Alignement des coordonnées de l'overlay (détail technique à valoriser)

Le Core détecte sur des frames **redimensionnées à 640×480** (`FRAME_SIZE`), donc les
bbox sont dans ce repère. La vidéo WebRTC, elle, est à la résolution native de la
caméra (p. ex. 1920×1080). Pour aligner l'overlay :

- Le payload `metadata` transporte `width`/`height` (le repère des bbox).
- Le `<canvas>` est dimensionné en **interne** à `width×height` ; on dessine les bbox
  **directement** dans ce repère.
- `<video>` et `<canvas>` sont en `position: absolute; inset:0; width:100%; height:100%`,
  la vidéo en `object-fit: fill`. Le navigateur **étire** identiquement (par axe) la
  vidéo et le canvas vers la même boîte d'affichage. Comme le 640×480 du Core est lui
  aussi un redimensionnement **par axe** de la frame caméra, les positions **normalisées
  coïncident** → alignement automatique, y compris au redimensionnement de la fenêtre.

---

## 5. Ce qui a changé, fichier par fichier

| Fichier | Changement |
|---|---|
| `docker-compose.yml` | **+ service `mediamtx`** (ports 8554 RTSP, 8889 WebRTC, 8189/udp ICE) ; env Core `READ_FROM_MEDIAMTX=true`, `MEDIAMTX_RTSP_BASE=mediamtx:8554` ; `depends_on: mediamtx` ; env frontend `NEXT_PUBLIC_MEDIAMTX_URL` |
| `mediamtx.yml` *(nouveau)* | Config MediaMTX : serveurs RTSP + WebRTC, `webrtcAdditionalHosts:[127.0.0.1]` (ICE joignable depuis l'hôte), path `cam3` (source via env, `sourceOnDemand`, **`rtspTransport: tcp`**), catch-all `all_others` |
| `.env` | **+ `MTX_PATHS_CAM3_SOURCE`** = URL RTSP **déchiffrée** de la caméra (injectée dans MediaMTX) |
| `core/web_streaming.py` | Supprime `cv2`/`base64`, le cache JPEG et l'événement **`frame`**. Le thread de broadcast envoie désormais l'événement **`metadata`** (JSON, dédup par `seq`). `/api/cameras` : statut « online » basé sur `result_metadata` |
| `core/tracking_processor.py` | **Plus aucun dessin** : suppression de `annotate_frame`, `add_camera_overlay`. La boucle construit une **liste de détections JSON** (visages) + appelle le LPR, et écrit `result_metadata[cam_id]`. (Worker reconnaissance fire-and-forget conservé) |
| `core/plate_processor.py` | `process()` ne **dessine plus** (met à jour `plate_db`) ; **+ `get_detections()`** qui renvoie les plaques en JSON ; suppression de `_annotate` / `annotate_cached` |
| `core/surveillance_system.py` | **+ dictionnaire partagé `result_metadata`** (par caméra), passé au `TrackingProcessor` |
| `core/camera_manager.py` | Si `READ_FROM_MEDIAMTX`, la source de capture devient `rtsp://<base>/cam<id>` au lieu de `cam["rtsp_url"]` (log de la source choisie) |
| `config/settings.py` | **+ `READ_FROM_MEDIAMTX`** (bool) et **+ `MEDIAMTX_RTSP_BASE`** |
| `app/.../live/CameraStream.js` | Réécrit : **client WHEP** → `<video>` ; **`<canvas>` transparent** superposé ; écoute `metadata` et dessine les boîtes (mise à l'échelle automatique) ; suppression de tout le rendu d'images |

> **Hors streaming, mais à signaler dans le mémoire** : un correctif d'infrastructure a
> rendu **InsightFace réellement exécuté sur GPU** (CUDAExecutionProvider). Le paquet CPU
> `onnxruntime` (tiré en dépendance par `insightface`) écrasait le binaire d'`onnxruntime-gpu` ;
> le `Dockerfile` du Core purge maintenant le paquet CPU et réinstalle `onnxruntime-gpu`,
> avec un **garde-fou de build**. → la détection/reconnaissance faciale tourne sur le GPU.

---

## 6. Protocoles : qui utilise quoi ?

| Lien | Protocole | Détail |
|---|---|---|
| Caméra → MediaMTX | **RTSP / TCP** | 1 connexion, à la demande (`sourceOnDemand`), `rtspTransport: tcp` |
| MediaMTX → Core | **RTSP / TCP** | réseau interne Docker, sans perte (`rtsp://mediamtx:8554/cam3`) |
| MediaMTX → Navigateur | **WebRTC (WHEP)** | vidéo H.264 décodée nativement par le navigateur ; signalisation HTTP `:8889`, ICE UDP `:8189` |
| Core → Navigateur | **WebSocket (Socket.IO)** | événement **`metadata`** (bounding boxes JSON) — **toujours utilisé** |
| Navigateur → Core | **HTTP REST** | `/api/lpr/status`, `/api/lpr/toggle`, `/api/cameras`, `/api/stats` |
| Core → Backend | **HTTP REST** | recherche FAISS (`/people/search`), création d'événement (`/events/add`) — en fire-and-forget |

**Événements Socket.IO actuels** : `connect` → `cameras_list` ; `start_stream {camera_id}` ;
`stop_stream` ; **`metadata`** (← remplace l'ancien `frame`). L'événement `frame` n'existe **plus**.

---

## 7. Configuration & variables d'environnement

| Variable | Où | Rôle |
|---|---|---|
| `MTX_PATHS_CAM3_SOURCE` | `.env` → service `mediamtx` | URL RTSP **déchiffrée** de la caméra 3 (MediaMTX y mappe `paths.cam3.source`) |
| `READ_FROM_MEDIAMTX` | compose → `core` | `true` = le Core lit le flux republié par MediaMTX (connexion caméra unique) |
| `MEDIAMTX_RTSP_BASE` | compose → `core` | hôte:port RTSP interne (`mediamtx:8554`) |
| `NEXT_PUBLIC_MEDIAMTX_URL` | compose → `frontend` | base WHEP côté navigateur (`http://localhost:8889`) |
| `NEXT_PUBLIC_SOCKET_URL` | compose → `frontend` | Socket.IO du Core pour les métadonnées (`http://localhost:5000`) |

**Convention multi-caméras** : caméra d'`id = N` → path MediaMTX `camN` → le Core lit
`rtsp://mediamtx:8554/camN`, le navigateur lit `…:8889/camN/whep`. Pour ajouter une
caméra : déclarer `camN` dans `mediamtx.yml` (+ `MTX_PATHS_CAMN_SOURCE` dans `.env`).

---

## 8. Mises à jour à apporter au mémoire (`ANALYSE_TECHNIQUE_OSIRION.md`)

Les passages ci-dessous décrivent l'**ancienne** architecture et doivent être corrigés
(numéros de ligne indicatifs au moment de la rédaction de ce document) :

| Ligne(s) | Texte actuel (obsolète) | À remplacer par |
|---|---|---|
| **§3.1 (≈ L126)** | « **4 services** conteneurisés » | « **5 services** » (ajout de **MediaMTX**) |
| **L80** | « Streaming WebSocket (Flask-SocketIO) : diffusion des **frames annotées (JPEG/base64)** … cache JPEG » | « **Métadonnées** (bounding boxes JSON) en Socket.IO (`metadata`) ; **vidéo en WebRTC** via MediaMTX » |
| **L92 / L185** | « visualisation live (**canvas + socket.io**) » | « **`<video>` WebRTC** + **`<canvas>` overlay** ; Socket.IO pour les métadonnées » |
| **L103** | « Pipeline live : … → **streaming WebSocket** » | « … → **métadonnées Socket.IO** ; vidéo **WebRTC** (MediaMTX) » |
| **L114** | « le **flux vidéo** n'est pas protégé par JWT côté Socket.IO » | « le flux vidéo passe par **WebRTC/MediaMTX** (sans auth) ; Socket.IO ne transporte **que** des métadonnées (toujours sans auth) » |
| **L136 (schéma)** | flèche « WebSocket (socket.io) » pour la vidéo | ajouter **WebRTC (vidéo)** + **Socket.IO (métadonnées)** |
| **L150 (tableau services)** | « core … Traitement vidéo temps réel + **streaming** » | « core … temps réel + **métadonnées** » **et ajouter une ligne `mediamtx`** |
| **L168 / L174** | `web_streaming.py` « **broadcast frames** » | « **broadcast métadonnées** (`metadata`) » |
| **L206** | « la **frame annotée** est stockée (`result_frames`) et **diffusée** » | « les **détections** sont stockées (`result_metadata`) et diffusées en `metadata` ; **la frame n'est plus ni annotée ni diffusée** » |
| **L209** | « reçoit l'événement **`frame` (JPEG base64) à ~30 FPS**, dessine sur un `<canvas>` » | « **lit la vidéo en WebRTC** ; reçoit **`metadata`** (~10/s) et **dessine les boîtes** sur un `<canvas>` superposé » |
| **L233 (techno)** | tableau des technos | ajouter **MediaMTX** et **WebRTC (WHEP)** ; préciser Flask-SocketIO = **métadonnées** |
| **L318 / L401 (séquences)** | « WebStreamingServer → Socket.IO **'frame'** → navigateur » | « WebStreamingServer → Socket.IO **'metadata'** → navigateur (+ **MediaMTX → WebRTC → `<video>`**) » |
| **L325** | « cache JPEG partagé entre clients » | supprimer (plus de JPEG) ; mentionner la **dédup par `seq`** des métadonnées |
| **L669-709 (UML)** | classes/séquence `WebStreamingServer` (frames) | mettre à jour : `metadata`, `result_metadata`, ajout `MediaMTX` |

> 💡 Pour le mémoire, c'est un **excellent angle** : montrer l'évolution d'une architecture
> « moteur IA qui fait tout » vers une **architecture VMS découplée** (séparation du
> transport vidéo et des métadonnées), avec justification chiffrée (cf. §9).

---

## 9. Bénéfices mesurés

- **Vidéo** : décodage **natif/accéléré** par le navigateur (H.264), fluide, au lieu de
  redessiner des JPEG. Latence et bande passante réseau **sorties du Core**.
- **CPU Core** : suppression de `cv2.imencode` **par frame** + de tout le dessin/`memcpy`.
  Le Core ne fait plus que l'inférence GPU + un petit JSON.
- **Pertes réseau** : passage de MediaMTX en **RTSP/TCP** → **0 paquet RTP perdu** mesuré
  sur 25-30 s (contre des centaines/seconde en UDP) ; **0 erreur de décodage** côté Core.
- **Charge caméra** : **1 seule** connexion RTSP à la caméra physique (au lieu de 2).
- **GPU** : InsightFace tourne bien sur **CUDA** (≈ 0,6-0,7 Go VRAM en charge).

> ⚠️ Les valeurs ci-dessus sont des **observations** (logs MediaMTX/Core, `docker stats`,
> `nvidia-smi`) et non un **benchmark formel** — à présenter comme tel dans le mémoire 🟡.

---

## 10. Limites & pistes d'amélioration

- **Sécurité MediaMTX** : ni le WebRTC (WHEP) ni le RTSP republié ne sont **authentifiés**
  (catch-all `all_others` permissif). Acceptable en `localhost`/démo ; **ajouter
  l'authentification MediaMTX** (utilisateurs publish/read) avant toute exposition réseau.
- **Authentification Socket.IO** : le canal `metadata` n'est toujours pas protégé par JWT.
- **Multi-caméras** : chaque caméra doit être déclarée dans `mediamtx.yml` (+ `.env`).
  Une évolution possible : un petit service qui configure les paths MediaMTX dynamiquement
  via son API à partir de la liste de caméras du backend.
- **Cadence de l'overlay** : les boîtes sont mises à jour à la cadence d'inférence
  (~10/s) tandis que la vidéo est fluide (≥ 25 FPS). Possibilité d'**interpoler** les
  positions côté client pour un rendu plus lisse.
- **Robustesse réseau caméra** : le lien vers la caméra doit rester en **TCP** (l'UDP
  perdait massivement des paquets sur ce matériel).

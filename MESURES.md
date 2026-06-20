# Protocole de mesure — Chapitre 4 (Osirion)

Ce document décrit, **pas à pas**, les actions à réaliser **hors-ligne** (sur le
réseau du NVR, sans internet) pour produire les chiffres des tableaux **4.4**
(facial), **4.5** (multi-caméras) et **4.6** (plaques).

Tout est journalisé automatiquement dans **`measurements/metrics.jsonl`** (sur
l'hôte, via bind mount). Au retour en ligne, on lance le script d'analyse — ou on
me transmet le fichier — pour obtenir les valeurs prêtes à coller.

> Portée : petit N (2 personnes enrôlées, 3 plaques) → résultats **« à l'échelle
> prototype »**, à présenter comme tels (cohérent avec la rigueur du mémoire).
> Colonne GPU uniquement (la colonne CPU reste « à mesurer »).

---

## 0. Préparation (À FAIRE PENDANT QUE TU AS ENCORE INTERNET)

```bash
cd ~/Documents/Osirion
chmod +x mesure.sh

# 1) Recharger le Core avec l'instrumentation + monter le dossier measurements.
#    (le bind mount ./measurements est NOUVEAU → il faut RECRÉER le conteneur)
docker compose up -d core

# 2) Vérifier que le journal de mesure est actif (doit répondre enabled:true)
./mesure.sh status

# 3) Vérifier que le fichier se crée et se remplit (laisse tourner ~10 s)
./mesure.sh count          # doit lister au moins 'system_sample' et 'session_start'
```
Si `status` renvoie `enabled:false`, vérifier `MEASURE_ENABLED` dans `.env`/compose.

Une fois sur le réseau du NVR, **vérifie que les 4 caméras diffusent** (page
caméras du frontend) avant de commencer.

---

## 1. Tableau 4.5 — Scalabilité multi-caméras (+ latence/FPS de 4.4)

Objectif : débit, latence, taux de cache et GPU pour **1, puis 2, puis 4 caméras**.
On change le nombre de caméras **actives** depuis la page *Caméras* du frontend
(bouton activer/désactiver), puis on laisse tourner ~5 min par palier.

> Le Core applique les (dés)activations en ~15 s. Attends ~20 s après chaque
> changement **avant** de marquer le scénario.

```bash
# Palier 1 caméra : désactive 3 caméras dans le frontend, garde-en 1 active. Attends 20 s.
./mesure.sh mark "scalabilite-1cam"
#   → marche devant la caméra, laisse tourner 5 min (people in/out pour solliciter le cache)

# Palier 2 caméras : réactive une 2e caméra. Attends 20 s.
./mesure.sh mark "scalabilite-2cam"
#   → 5 min

# Palier 4 caméras : réactive toutes les caméras. Attends 20 s.
./mesure.sh mark "scalabilite-4cam"
#   → 5 min
```
Ces 3 paliers remplissent **4.5** (colonnes 1 / n / n′ caméras) et donnent aussi
la **latence facial (ms/frame)** et le **débit/caméra (FPS)** du **4.4** (colonne GPU).

---

## 2. Tableau 4.4 — Précision du module facial

Objectif : rang-1, précision/rappel/F1, EER. On déclare la **vérité terrain**
(qui est devant la caméra) avec `expect`, puis la personne se présente.

> Astuce échantillons : fais **entrer/sortir** la personne du champ plusieurs fois
> (chaque nouvelle apparition = une nouvelle décision FAISS « fraîche » utilisée
> pour l'EER). Vise ≥ 15–20 apparitions par personne.

```bash
./mesure.sh mark "facial-precision"

# Personne 1 (enrôlée) — remplace 6 par l'ID réel de la caméra utilisée
./mesure.sh expect 6 "NOM_PERSONNE_1"
#   → la personne 1 se présente, entre/sort du champ ~2–3 min

# Personne 2 (enrôlée)
./mesure.sh expect 6 "NOM_PERSONNE_2"
#   → la personne 2 se présente ~2–3 min

# IMPOSTEUR (indispensable pour FAR / EER) : une personne NON enrôlée
./mesure.sh expect 6 "Inconnu"
#   → la personne non enrôlée se présente ~2–3 min

./mesure.sh unexpect 6     # fin du volet facial : on efface la vérité terrain
```
> Utilise les noms **exacts** tels qu'enrôlés (le script compare candidat vs
> attendu). Sans le volet imposteur, l'EER ne pourra pas être calculé.

---

## 3. Tableau 4.6 — Module plaques (mono-image vs vote temporel)

Objectif : CER + exactitude plaque entière, mono-image vs vote, latence LPR,
recherche floue. Prérequis : **activer le LPR** et présenter les plaques simulées.

```bash
# Activer le module plaques (LPR)
curl -fsS -X POST http://localhost:5000/api/lpr/toggle \
     -H 'Content-Type: application/json' -d '{"enabled":true}'; echo

./mesure.sh mark "plaques"

# Pour CHAQUE plaque : déclarer la vérité terrain puis la présenter plusieurs fois
./mesure.sh plate "BB4060"
#   → présente la plaque BB4060 (simulateur voiture), plusieurs passages, ~2 min

./mesure.sh plate "CJ2179"
#   → présente CJ2179, plusieurs passages, ~2 min

./mesure.sh plate "AF6283"
#   → présente AF6283, plusieurs passages, ~2 min

./mesure.sh unplate        # fin du volet plaques
```
> Chaque plaque finalisée produit un événement `plate_read` qui compare la
> **lecture mono-image** (1ʳᵉ passe OCR) au **consensus voté** → remplit les deux
> colonnes du 4.6. Multiplie les passages pour avoir assez de lectures.

---

## 4. Fin de campagne

```bash
./mesure.sh count          # récapitulatif : doit montrer system_sample, recognition,
                           # plate_read, plate_lookup, mark, groundtruth…
```
Le fichier **`measurements/metrics.jsonl`** est déjà sur l'hôte : **ne pas le
supprimer**. (Optionnel : en faire une copie horodatée.)

---

## 5. Au retour en ligne — dépouillement

```bash
python3 tools/analyze_metrics.py measurements/metrics.jsonl
# ou un seul scénario :
python3 tools/analyze_metrics.py --scenario "scalabilite-4cam"
```
Le script imprime, par scénario, les valeurs des tableaux 4.4 / 4.5 / 4.6.
Tu peux aussi me transmettre `measurements/metrics.jsonl` : je le dépouille et je
remplis directement les tableaux du mémoire.

---

### Aide-mémoire des commandes

| Action | Commande |
|---|---|
| État courant | `./mesure.sh status` |
| Nouveau scénario | `./mesure.sh mark "<libellé>"` |
| Vérité terrain visage | `./mesure.sh expect <cam_id> "<Nom>"` |
| Imposteur | `./mesure.sh expect <cam_id> Inconnu` |
| Effacer visage | `./mesure.sh unexpect <cam_id>` |
| Vérité terrain plaque | `./mesure.sh plate "<PLAQUE>"` |
| Effacer plaque | `./mesure.sh unplate` |
| Suivre le journal | `./mesure.sh tail` |
| Compter les événements | `./mesure.sh count` |

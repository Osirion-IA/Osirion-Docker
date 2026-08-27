# Campagne d'observation 24–48 h

La campagne conserve trois familles de preuves complémentaires :

- les événements et alertes métier, avec leurs captures habituelles ;
- un échantillon `PRESENCE_AUDIT_SAMPLE` toutes les deux minutes par poste et
  uniquement pendant les horaires travaillés ;
- les performances système toutes les 30 secondes : FPS traitées, latences
  d'inférence et de frame, santé caméra et occupation GPU.

Les échantillons techniques sont masqués du journal général par défaut afin de
ne pas repousser les événements métier hors des 500 dernières lignes. Ils restent
interrogeables avec `event_types=PRESENCE_AUDIT_SAMPLE` ou `include_audit=true`.

## Démarrage

```bash
RUN_ID=eval_$(date -u +%Y%m%dT%H%M%SZ)
OBSERVATION_RUN_ID="$RUN_ID" docker compose \
  -f docker-compose.yml -f docker-compose.observation.yml \
  up -d --force-recreate
docker compose -f docker-compose.yml -f docker-compose.observation.yml exec -T \
  backend python /app/scripts/observation_bundle.py start --run-id "$RUN_ID"
```

Le dossier local `observation_runs/$RUN_ID/` reçoit le manifeste et les métriques.
Il est ignoré par Git et ne contient aucune URL RTSP ni aucun identifiant secret.

## Contrôle pendant la campagne

```bash
docker compose -f docker-compose.yml -f docker-compose.observation.yml exec -T \
  backend python /app/scripts/observation_bundle.py status
```

Surveiller également l'espace libre avec `df -h .`. L'estimation initiale pour
neuf postes est de 0,4 à 0,5 Go de captures par journée travaillée.

## Clôture et export

```bash
docker compose -f docker-compose.yml -f docker-compose.observation.yml exec -T \
  backend python /app/scripts/observation_bundle.py export
docker compose up -d --force-recreate
```

Le bundle final contient les événements, alertes, transitions de santé caméra,
configurations métier de début et de fin, métriques système et toutes les captures
référencées. Le second `docker compose` redémarre le mode normal et désactive les
échantillons périodiques.

## Critères à analyser

- faux postes vacants : agent visible dans le polygone sur une alerte ;
- faux négatifs : poste vide sur un échantillon mais sans épisode signalé ;
- délai réel de signalement et cohérence ouverture/clôture ;
- disponibilité par caméra et périodes `offline`/`stalled` ;
- pertes d'événements ou captures manquantes ;
- FPS, latences p50/p95 et saturation GPU sur toute la période.

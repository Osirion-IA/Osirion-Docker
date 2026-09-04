# Plan de corrections avant la campagne 2

**Objectif.** Corriger tout ce que la campagne `eval_20260827T145943Z` a révélé, **puis seulement**
relancer une campagne d'observation. La campagne 1 a mesuré une panne d'ingestion vidéo et un
planning fictif ; la campagne 2 doit mesurer le métier.

**Règle qui gouverne ce plan.** Aucune campagne longue ne redémarre tant que la
[porte de contrôle](#porte-de-contrôle--à-passer-avant-toute-relance) n'est pas franchie
intégralement. Chaque critère y est objectif et vérifiable par une commande. Un critère non
vérifié compte comme non satisfait.

## Relecture corrective Codex — 4 septembre 2026

La relecture a découvert puis corrigé une régression qui invalidait le premier
test de fumée : MediaMTX renvoie `3m0s` après réception de `180s`. La comparaison
textuelle repatchait donc tous les chemins à chaque réconciliation (338 PATCH en
10 minutes). Les durées sont désormais normalisées ; après redéploiement, zéro
PATCH récurrent et zéro timeout ont été observés, avec 14 caméras sur 15 en ligne.

Autres corrections finalisées :

- les canaux demandés par la règle sont conservés sur l'alerte ; un canal ajouté
  plus tard ne reçoit pas rétroactivement une alerte ;
- les 61 échecs historiques sont marqués non délivrés et trop anciens, sans envoi
  tardif ; les nouveaux échecs suivent la reprise 1/5/15/30 minutes ;
- la rétention est désactivée par défaut et préserve toute capture référencée par
  une alerte ;
- les épisodes clos autrement que par `presence_restored` sont exclus des
  agrégats par défaut, y compris l'historique mal marqué `reliable` ; le cumul de
  référence passe de 32,12 h brutes à 14,88 h fiables ;
- l'API et l'interface affichent l'état, les tentatives et la dernière erreur de
  notification ;
- les métriques de campagne incluent désormais la santé de l'API MediaMTX, le
  nombre de chemins gérés et l'espace disque ;
- quatre groupes provisoires H24 ont été créés avec leurs fuseaux réels : Niger,
  Bénin, Mali et Togo. Ils servent à la validation technique, pas encore à une
  évaluation RH des agences dont les horaires réels sont inconnus ;
- la caméra 89 est rattachée à Lomé et la caméra 106 reste surveillée H24 ;
- la campagne 1 est clôturée au dernier échantillon réellement écrit :
  `2026-09-03T11:24:01.219000+00:00`.

Validation : 35 tests backend, 41 tests Core et build Next.js de production
réussis. La rétention active vaut `0`.

- Rapport d'évaluation source : <https://claude.ai/code/artifact/3c0aa33d-dcf9-490c-afb6-fa5bf790b54d>
- Relève précédente : `HANDOFF_ANALYSE_CAMPAGNE_2026-09-03.md`
- Preuves d'audit : `audit_vacances_2026-09-03/`
- Cutoff de référence de la campagne 1 : `2026-09-03 11:30:00 UTC`

---

## Vue d'ensemble

| Lot | Objet | Bloquant | État au 2026-09-04 |
|---|---|:--:|---|
| **A** | Chaîne vidéo — débloquer l'ingestion | **Oui** | ✅ **Terminé** — 78,8 % → 0 % d'échec de relais |
| **B** | Fiabilité des alertes | **Oui** | 🟡 File de reprise faite ; affichage UI et canal de repli restants |
| **C** | Vérité métier — horaires et fuseaux | **Oui** | ⛔ **Bloqué** — arbitrage métier requis |
| **D** | Honnêteté des données d'absence | **Oui** | 🟡 Qualification faite ; agrégats restants |
| **E** | Exploitation — disque et rétention | **Oui** | 🟡 Rétention et surveillance faites ; archivage restant |
| **F** | Documentation des limites connues | Non | ⬜ À faire |
| **G** | Instrumentation de la campagne 2 | **Oui** | ⬜ À faire (après A→E) |

Les titres de section portent le même code : ✅ fait et vérifié · 🟡 partiellement fait ·
⬜ à faire · ⛔ bloqué par une décision.

---

## État au 4 septembre 2026

### Le résultat obtenu

| Étape | Démarrages de relais | Timeouts | Taux d'échec | Caméras en ligne |
|---|---:|---:|---|---|
| Campagne `eval_20260827T145943Z` | 9 202 | 7 251 | **78,8 %** | médiane 10/15 |
| Contrôle 2 h, avant correctifs | 68 | 46 | **67,6 %** | — |
| Après A1 + A2 | 56 | 14 | **25,0 %** | 5 en ligne, 8 figées |
| **Après `closeAfter` 180 s (24 min)** | **12** | **0** | **0,0 %** | **12 à 14 / 15** |

Le nombre de démarrages s'effondre de 56 à 12 sur une durée comparable : un par caméra, puis plus
rien. Le cycle de relance permanent a disparu.

> **Nuance à ne pas gommer.** L'état instantané des caméras oscille encore (14/15 puis 12/15 avec
> 2 en connexion). C'est attendu : la passerelle HikCentral reste imparfaite et les caméras vont et
> viennent. Ce qui a changé, c'est qu'Osirion **n'amplifie plus** ces incidents — une caméra qui
> décroche n'entraîne plus la destruction puis la redemande de sa session, et ne pénalise donc plus
> les autres.

### Inventaire des modifications

**Core** (`Osirion-core-master/Osirion-core-master/`)

| Fichier | Lot | Modification |
|---|---|---|
| `services/mediamtx_path_service.py` | A1, A3 | Suppression du chemin condamné (garde `healthy`) ; comparaison de la configuration **complète** et non de la seule commande `runOnDemand` |
| `services/hik_stream_resolver.py` | A2, A4 | Disjoncteur partagé + `resolver_health()` |
| `core/surveillance_system.py` | A1, A4 | `_healthy_camera_ids()` ; bloc `ingest` dans `system_sample` |
| `config/settings.py` | A3 | `MEDIAMTX_ON_DEMAND_CLOSE_AFTER` : `30s` → `180s` |
| `core/event_engine.py` | D1 | `presence_data_quality` dérivé du motif de clôture |
| `core/tests/test_stream_resilience.py` | A | **Nouveau** — 12 tests |
| `core/tests/test_presence_schedule.py` | D1 | +1 test de qualification |

**Backend** (`Osirion-backend-main/Osirion-backend-main/`)

| Fichier | Lot | Modification |
|---|---|---|
| `app/services/retention_scheduler.py` | E1, E2 | **Nouveau** — thread de rétention + `disk_usage()` |
| `app/services/notification_retry.py` | B1 | **Nouveau** — thread de reprise des envois |
| `app/services/rule_engine.py` | B1 | Enregistrement de l'échec + programmation d'une reprise |
| `app/models/alerts.py` | B1 | `notify_attempts`, `notify_last_error`, `notify_next_retry_at` |
| `alembic/versions/64b322f7fbe8_alert_notify_retry.py` | B1 | **Nouveau** — migration, **appliquée** |
| `app/routes/maintenance_routes.py` | E1, E2 | `GET /maintenance/disk` ; purge partagée avec la rétention |
| `app/config.py` | B1, E | Nouveaux réglages (ci-dessous) |
| `app/main.py` | B1, E1 | Démarrage des deux threads |
| `app/tests/test_notification_retry.py` | B1 | **Nouveau** — 7 tests |

### Réglages ajoutés

Tous ont un défaut utilisable ; aucun n'est obligatoire dans `.env`.

| Réglage | Défaut | Rôle | Mettre à 0 pour |
|---|---|---|---|
| `MEDIAMTX_ON_DEMAND_CLOSE_AFTER` | `180s` | Durée pendant laquelle le relais reste tiède sans lecteur | — |
| `HIK_RESOLVE_FAIL_THRESHOLD` | `3` | Échecs consécutifs avant ouverture du disjoncteur | — |
| `HIK_RESOLVE_BACKOFF_BASE` | `30` | Délai initial de suspension (s) | — |
| `HIK_RESOLVE_BACKOFF_MAX` | `300` | Plafond de suspension (s) | — |
| `RETENTION_DAYS` | `30` | Conservation des événements et captures | désactiver la purge auto |
| `RETENTION_CHECK_HOURS` | `24` | Fréquence du cycle de rétention | — |
| `RETENTION_MIN_FREE_GB` | `10` | Seuil d'alerte disque (log ERROR) | — |
| `NOTIFY_RETRY_SECONDS` | `60` | Cycle de reprise des notifications | désactiver la reprise |

### Vérification

```bash
# Core — 39 tests
docker run --rm -v "$PWD/Osirion-core-master/Osirion-core-master":/src:ro -w /src \
  -e API_URL=http://backend:8000/ -e CORE_API_KEY=test-only -e PYTHONDONTWRITEBYTECODE=1 \
  osirion-core:gpu python -m unittest discover -s core/tests -t .

# Backend — 31 tests
docker compose exec -T -w /app backend python -m unittest discover -s app/tests -t .
```

Au 2026-09-04 : **70 tests, tous verts**. Les modules `core/` et `services/` étant montés en bind,
un `docker compose restart core` suffit à appliquer les changements du Core — pas de rebuild.

### Pièges rencontrés, à connaître

**Les identifiants de migration Alembic sont recyclés.** Ils sont écrits à la main et plusieurs
fichiers partagent le même (`a1b2c3d4e5f6`, `c3d4e5f6a7b8`…). Deux collisions successives ont
produit un `Cycle is detected in revisions` trompeur. Avant toute nouvelle migration :

```bash
python3 -c "
import re, glob, secrets
pris = set()
for f in glob.glob('alembic/versions/*.py'):
    pris |= set(re.findall(r'[0-9a-f]{12}', open(f).read()))
while True:
    c = secrets.token_hex(6)
    if c not in pris: print(c); break
"
```

Penser aussi à supprimer le `.pyc` obsolète dans `alembic/versions/__pycache__/` après un renommage.

**Les logs `INFO` applicatifs n'apparaissent pas dans `docker compose logs`.** La configuration
uvicorn ne propage que `warning` et `error`. Le démarrage des threads de fond est donc invisible :
pour vérifier, appeler la fonction directement plutôt que chercher le message dans le journal.

**Les tests backend qui instancient un modèle doivent importer tout `app.models`.** Instancier un
`Alert` déclenche la configuration des mappers SQLAlchemy, qui exige que `CameraGroup` soit chargé.
Sans cet import, les tests passent isolément et échouent en découverte, selon l'ordre de chargement.

---

## Lot A — Chaîne vidéo

> Cause racine établie : la passerelle HikCentral refuse la résolution d'URL (44 902 fois en
> 7 jours, `HTTP 502`) ; le relais ffmpeg est alors relancé en boucle sans jamais publier.
> Résultat : 78,8 % des relais meurent en délai de démarrage et le parc est indisponible
> 34,3 % du temps.

### ⚠ Correction du diagnostic — 2026-09-04

Les mesures faites en implémentant ce lot **invalident une partie de l'explication initiale**.
Les faits observés ne changent pas ; leur interprétation, si.

**Ce qui était faux.** Le rapport d'évaluation attribuait l'échec des relais à un *jeton d'accès
périmé* laissé dans le chemin MediaMTX. Vérifié sur la passerelle réelle :

- l'URL `rtsp_s` d'une caméra est **stable** — une résolution forcée renvoie exactement la même
  chaîne que celle déjà stockée (empreintes SHA-256 identiques sur cam9, cam24, cam65, cam106) ;
- son jeton est **réutilisable** — trois lectures successives avec la même URL réussissent ;
- une caméra seule démarre en **2 secondes**.

Donc « zéro `PATCH` en sept jours » n'était pas un bug : il n'y avait rien à mettre à jour.

**Ce qui est vrai.** Le point de rupture est l'**établissement de session côté passerelle, sous
charge concurrente** :

| Sondes RTSP simultanées | Réussites |
|---:|---|
| 2 | 2/2 — 100 % |
| 6 | 5/6 — 83 % |
| 12 | 10/12 — 83 % |

La passerelle accepte la connexion puis la referme ; ffmpeg sort aussitôt en code 0 sans rien
publier ; `runOnDemandStartTimeout` expire ; le lecteur du Core est éjecté, se reconnecte, et
`runOnDemandRestart` rejoue le relais toutes les ~6 s. **Une défaillance de ~17 % à l'établissement
était amplifiée en 78,8 % par cette boucle de relance.**

**Conséquence sur le plan.** A1 et A2 restent justifiés — ils suppriment l'amplification, qui est
la part maîtrisable — mais ils ne peuvent pas dépasser le plafond imposé par la passerelle. A3
(résolution groupée) passe de « recommandé » à **important** : réduire le nombre de sessions
concurrentes attaque enfin la cause, et non plus seulement son amplification.

### Résultats mesurés après A1 + A2 (26 min, en production)

| Périmètre | Démarrages | Timeouts | Taux d'échec |
|---|---:|---:|---|
| Avant correctifs (campagne) | 9 202 | 7 251 | **78,8 %** |
| Avant correctifs (2 h, 2026-09-03) | 68 | 46 | **67,6 %** |
| Après A1+A2, toutes caméras | 56 | 14 | **25,0 %** |
| Après A1+A2, **hors cam24** | 44 | 2 | **4,5 %** ✅ |
| cam24 seule | 12 | 12 | **100 %** |

**Le défaut systémique est corrigé** : hors cam24, le taux passe sous le seuil de 5 % de la porte
de contrôle. Le résidu tient à **une seule caméra**, déjà la pire de la campagne (95,7 %).

> **Le critère de la porte de contrôle doit être évalué par caméra, pas en moyenne** — sans quoi
> une seule caméra défaillante masque le résultat de tout le parc.

### Le correctif décisif : garder le relais tiède

Le résidu de cam24 a mis sur la piste du vrai coupable, et il n'était ni A1 ni A2.

`runOnDemandCloseAfter` valait **30 s** : dès que le lecteur du Core décrochait un instant, le
relais était tué, puis redemandé à la passerelle quelques secondes plus tard. Mesuré en
production : **190 arrêts « plus aucun lecteur » pour 189 relances, dont 87 % en moins de trois
minutes** (médiane 54 s). Or la passerelle échoue à l'ÉTABLISSEMENT de session, pas à la tenir :
ce cycle était donc la pire sollicitation possible.

Deux corrections liées :

1. `MEDIAMTX_ON_DEMAND_CLOSE_AFTER` passe de `30s` à **`180s`** — le relais reste tiède et absorbe
   les décrochages brefs, transformant un flot de connexions en sessions stables.
2. `sync_paths` ne comparait que la commande `runOnDemand` : **aucun autre réglage ne se propageait
   jamais** aux chemins existants. Sans ce correctif, le changement ci-dessus n'aurait pris effet
   qu'au prochain redémarrage de MediaMTX.

| Étape | Démarrages | Timeouts | Taux | Caméras en ligne |
|---|---:|---:|---|---|
| Campagne (référence) | 9 202 | 7 251 | 78,8 % | médiane 10 / 15 |
| Après A1 + A2 | 56 | 14 | 25,0 % | 5 en ligne, 8 figées |
| **Après `closeAfter` 180 s** | **12** | **0** | **0,0 %** | **14 / 15** ✅ |

Le nombre de démarrages s'effondre de 56 à 12 sur une durée comparable : un par caméra, puis plus
rien. **cam24 comprise** — son échec systématique venait de la relance permanente, pas d'un défaut
propre. La décision de terrain la concernant devient sans objet.

### A1 — Neutraliser le chemin vidéo quand l'URL ne se résout pas ✅

**Fichier.** `Osirion-core-master/Osirion-core-master/services/mediamtx_path_service.py`,
fonction `sync_paths()`.

**Ce qui se passe aujourd'hui.** Quand `rtsp_url` est vide, la boucle logue
`Caméra N sans rtsp_url — chemin MediaMTX camN ignoré` puis `continue`. Le chemin existant reste
en place **avec son ancien jeton mort**, et MediaMTX relance le relais dessus toutes les 6 s.

```python
# état actuel — le chemin mort survit
if not rtsp_url:
    logger.warning(f"Caméra {cam.get('id')} sans rtsp_url — chemin MediaMTX {name} ignoré.")
    continue
```

**Correction.** Si le chemin existe déjà et que l'URL ne se résout pas, **le supprimer**
(`_delete_path`) au lieu de le laisser. Il sera recréé proprement dès qu'une URL fraîche sera
disponible. Cela arrête net la boucle de relance et cesse de solliciter la passerelle.

**Point d'attention.** Ne supprimer que si le chemin **existe déjà** ; ne rien faire s'il n'a
jamais été créé (pas de bruit inutile). Journaliser en `warning` la suppression, avec le motif,
pour que le lot G puisse la compter.

**Critère d'acceptation.** Sur une coupure simulée de la passerelle, aucun
`runOnDemand command stopped: timed out` n'apparaît plus dans `logs-mediamtx/mediamtx.log` pour
les caméras dont l'URL n'est pas résolue.

---

### A2 — Freiner le résolveur quand la passerelle est en panne ✅

**Fichiers.** `core/surveillance_system.py` → `_resolve_hik_urls()` ;
`services/hik_stream_resolver.py` → `resolve_stream_url()`.

**Ce qui se passe aujourd'hui.** Dès qu'une caméra est en difficulté, le Core redemande une URL
avec `refresh=True`, ce qui **contourne le cache de 240 s** du backend. Avec 15 caméras en
difficulté simultanée et une supervision toutes les 15 s (`CAMERA_REFRESH_SECONDS`), la passerelle
déjà en 502 reçoit un flot de demandes forcées. **Le mécanisme de réparation alimente la panne.**

**Correction.** Introduire un **délai croissant partagé par toutes les caméras** (pas par caméra) :

1. Compter les échecs consécutifs de résolution, tous appareils confondus.
2. Au-delà d'un seuil (par ex. 3 échecs), suspendre les résolutions pendant un délai qui double
   à chaque nouvel échec, plafonné (par ex. 30 s → 5 min).
3. Ne jamais utiliser `refresh=True` pendant que le disjoncteur est ouvert : laisser le cache
   servir, il vaut mieux une URL peut-être périmée qu'un martèlement.
4. Réarmer immédiatement dès la première résolution réussie.

**Critère d'acceptation.** Sur une panne de passerelle de 10 minutes, le nombre d'appels à
`/hikcentral/stream-url` reste sous 30 (contre plusieurs centaines aujourd'hui).

---

### A3 — ~~Grouper les demandes d'URL~~ → Garder le relais tiède ✅

> **Abandonné tel qu'écrit, et remplacé.** La proposition initiale — un endpoint de résolution
> groupée — reposait sur une hypothèse **fausse** : `previewURLs` ne prend qu'**un seul**
> `cameraIndexCode` (vérifié dans `hikcentral_connector.get_preview_url`). Aucun regroupement
> n'est possible au niveau de l'API HikCentral.

En cherchant une alternative, la mesure a désigné une source de gaspillage bien plus grosse, décrite
en détail dans *[Le correctif décisif : garder le relais tiède](#le-correctif-décisif--garder-le-relais-tiède)*.
Résumé de ce qui a été fait :

1. `MEDIAMTX_ON_DEMAND_CLOSE_AFTER` : `30s` → **`180s`** (`config/settings.py`).
2. `sync_paths` compare désormais la **configuration complète** et non la seule commande
   `runOnDemand` — sans quoi le point 1 n'aurait jamais atteint les chemins existants.

**Résultat : 0 % d'échec de relais, 12 démarrages au lieu de 56.** C'est le correctif le plus
rentable des quatre, et il tient en deux lignes.

**Leçon de méthode.** Le premier A3 aurait été codé sur une hypothèse jamais vérifiée. Contrôler la
signature réelle de l'API avant d'écrire le plan aurait évité de proposer l'impossible — et de
passer à côté du vrai correctif.

---

### A4 — Rendre l'échec visible dans les métriques ✅

**Fichier.** `Osirion-core-master/Osirion-core-master/utils/measurement.py` (échantillon système).

**Pourquoi.** La campagne 1 n'a pas permis de voir le problème depuis les métriques : il a fallu
croiser 363 Mo de journaux MediaMTX. La campagne 2 doit être auto-diagnosticable.

**Correction.** Ajouter à chaque échantillon système, en plus des champs actuels :

- `hik_resolve_ok` / `hik_resolve_fail` — compteurs cumulés depuis le démarrage ;
- `hik_backoff_open` — booléen, disjoncteur A2 ouvert ou non ;
- `mediamtx_paths_active` — nombre de chemins réellement présents.

**Critère d'acceptation.** `metrics.jsonl` permet à lui seul de distinguer « passerelle en panne »
de « caméra individuelle en panne », sans lire les journaux MediaMTX.

---

## Lot B — Fiabilité des alertes

> 55 alertes de saturation de file perdues sur 500, en accélération. Les 74 alertes de poste
> vacant sont toutes parties, mais par chance : le mécanisme n'a aucun filet.

### B1 — Second canal et file de reprise 🟡

**Fichier.** `Osirion-backend-main/.../app/services/rule_engine.py`, `_send_notifications()`
(ligne ~256).

**Ce qui se passe aujourd'hui.** `notified_at` n'est posé que si au moins un canal aboutit. En cas
d'échec, l'exception est avalée par un `except Exception` qui logue un `warning`, et **l'alerte
n'est jamais réessayée**. Les deux règles actives n'ont qu'un seul canal, `email`, et
`alert_webhook_url` n'est pas configuré.

**Corrections, dans l'ordre.**

1. **Configurer un webhook de repli** dans Paramètres → Notifications. Correction de configuration,
   pas de code — à faire en premier car elle divise déjà le risque par deux.
2. **Persister l'échec** : ajouter à `Alert` les champs `notify_attempts` (int),
   `notify_last_error` (str) et `notify_next_retry_at` (datetime). Migration Alembic requise.
3. **Rejouer les envois échoués** : thread périodique sur le patron de
   `app/services/hikcentral_scheduler.py`, qui reprend les alertes sans `notified_at` dont
   `notify_next_retry_at` est échu, avec délai croissant et abandon après N tentatives.

**Critère d'acceptation.** Avec le serveur SMTP volontairement injoignable pendant 5 minutes,
aucune alerte n'est définitivement perdue : toutes portent `notified_at` après rétablissement.

### B2 — Rendre visible une alerte non délivrée ⬜

**Fichiers.** `app/routes/alerts_routes.py` (exposition, ligne ~45) et l'écran Alertes du frontend.

**Correction.** Afficher un état explicite « non notifiée » dans la liste des alertes, avec le
nombre de tentatives. Aujourd'hui une alerte perdue est **silencieuse** — rien dans l'interface ne
la distingue d'une alerte livrée.

---

## Lot C — Vérité métier : horaires et fuseaux

> 70 % des alertes tombent entre 19 h et 7 h locales, pic à 3 h du matin. Un seul régime horaire
> existe : « UTC+1 », `Africa/Niamey`, ouvert 24 h/24 sauf le vendredi de 13 h à 14 h, appliqué
> aux 9 zones de présence.

### ⚠ Décision métier requise avant tout code

Le planning permanent était **peut-être volontaire** pour la campagne 1, afin de collecter le
maximum de matière sans filtrer. Cette hypothèse est défendable et n'invalide rien.

**À trancher explicitement avant de modifier quoi que ce soit :**

1. Veut-on mesurer la présence **pendant les heures d'ouverture réelles** (recommandé — c'est le
   seul cadrage qui produit une donnée métier) ou **en continu** (surveillance de site) ?
2. Quelles sont les heures d'ouverture réelles de chaque agence, jour par jour, pauses comprises ?
3. Les postes de type magasin/réserve — la caméra 106 « RETRAIT MAGASIN » notamment — doivent-ils
   être surveillés comme des guichets ? **Recommandation : non.** Ce n'est pas un poste d'accueil ;
   ses 16 alertes sont techniquement justes et métier inutiles.

### C1 — Un régime horaire par fuseau ⛔

**Modèle.** `app/models/work_schedule.py` — le champ `timezone` (IANA) existe déjà, il suffit de
créer plusieurs enregistrements.

| Régime à créer | Fuseau IANA | Agences | Zones concernées |
|---|---|---|---|
| Niger | `Africa/Niamey` (UTC+1) | Diffa | 6, 9 |
| Bénin | `Africa/Porto-Novo` (UTC+1) | Cotonou | 4, 5 |
| Mali | `Africa/Bamako` (UTC+0) | Bamako | 12, 13 |
| Togo | `Africa/Lome` (UTC+0) | Lomé | 2, 3 |

> ⚠ `Africa/Cotonou` **n'existe pas** dans la base IANA — c'est `Africa/Porto-Novo`. Le
> commentaire de `work_schedule.py` le signale déjà.

### C2 — Rattacher les zones et qualifier la zone orpheline ⛔

Réaffecter `Zone.work_schedule_id` selon le tableau ci-dessus. **La zone 16 (caméra 89, « PR »)
n'a pas de localisation renseignée** — la qualifier avant de la rattacher, sans quoi elle restera
sur un fuseau arbitraire.

### C3 — Saisir de vraies plages d'ouverture ⛔

Remplacer `[["00:00","00:00"]]` (journée complète) par les plages réelles, une fois la décision
métier prise. Conserver `absence_tolerance_s` à 900 s sauf demande contraire : cette tolérance de
15 minutes a bien fonctionné sur la campagne 1.

**Critère d'acceptation.** Rejouer la distribution horaire des `POST_VACANT` de la campagne 1
contre les nouveaux plannings : la très grande majorité des 74 alertes doit tomber **hors créneau
travaillé**, donc ne plus être émise.

---

## Lot D — Honnêteté des données d'absence

> 44 des 74 épisodes (59,5 %, 17,2 h) sont clos par `camera_unavailable` — une panne technique,
> pas un retour d'agent — et sont pourtant marqués `presence_data_quality: "reliable"`.

### D1 — Qualifier la donnée selon le motif de clôture ✅

**Fichier.** `Osirion-core-master/Osirion-core-master/core/event_engine.py`,
`_close_post_episode()` (ligne ~909).

`presence_data_quality` y est **codé en dur** à `"reliable"` alors que `resolution_reason` est
déjà calculé juste à côté :

```python
"presence_data_quality": "reliable",   # ← inconditionnel
"resolution_reason": reason,           # ← "camera_unavailable" ou "presence_restored"
```

**Correction.** Dériver la qualité du motif : `reliable` uniquement si
`reason == "presence_restored"` ; sinon `truncated` (ou `unreliable`). Le champ
`snapshot_origin` est déjà honnête (`vacancy_frame_fallback`) — il n'y a rien à corriger de ce côté,
seulement à l'exploiter.

### D2 — Exclure les épisodes tronqués des agrégats métier ⬜

**Fichiers.** Services d'analytique du backend et écrans de présence du frontend.

Un épisode tronqué ne doit pas alimenter par défaut les durées d'absence affichées. Le proposer
en option (« inclure les épisodes interrompus »), jamais en valeur par défaut. Sans cela, une
panne vidéo se lit comme un mauvais comportement d'agent — c'est une accusation implicite fondée
sur un artefact technique.

**Critère d'acceptation.** Le tableau de bord d'absence recalculé sur la campagne 1 affiche
14,5 h (les 30 épisodes fiables) et non 31,8 h.

---

## Lot E — Exploitation : disque et rétention

> 7,9 Go de captures, 40 447 fichiers, ~800 Mo/jour. 14 Go libres sur une partition à 88 %.
> **Saturation sous une vingtaine de jours.** Aucune politique de rotation.

### E1 — Automatiser la purge existante ✅

**Bonne nouvelle : le mécanisme existe déjà.** `app/routes/maintenance_routes.py` expose
`purge-preview` et `purge-events` (suppression des événements antérieurs à N jours **et** de leurs
captures sur disque). Il est volontairement **manuel et destructif**.

**Correction.** Ajouter un thread périodique de rétention sur le patron de
`hikcentral_scheduler.py`, réutilisant la logique de `purge_events`, piloté par deux variables
d'environnement :

- `RETENTION_DAYS` (par ex. 30) — 0 désactive ;
- `RETENTION_CHECK_HOURS` (par ex. 24).

Journaliser chaque passage (nombre d'événements et de fichiers supprimés).

### E2 — Surveiller l'espace disque ✅

Ajouter l'espace libre de la partition des captures à l'échantillon système du lot A4, et une
alerte d'exploitation sous un seuil (par ex. 10 Go). La campagne 1 s'est déroulée sans aucune
visibilité sur ce point.

### E3 — Libérer de l'espace avant la campagne 2 ⬜

**14 Go ne suffisent pas** pour une campagne de 7 jours avec audit toutes les 2 minutes.
Avant relance, choisir explicitement :

- purger les captures antérieures à la remise à zéro du 20 août 2026 ; **et/ou**
- archiver hors disque système le `metrics.jsonl` et les captures de la campagne 1 ; **et/ou**
- allonger `PRESENCE_AUDIT_INTERVAL_SECONDS` de 120 s à 300 s (divise par 2,5 le volume d'audit).

> ⚠ Ne **jamais** purger les données de la campagne 1 sans les avoir archivées : elles sont la
> référence de comparaison de la campagne 2.

---

## Lot F — Documenter les limites connues

Non bloquant pour la relance, mais indispensable avant tout déploiement réel.

### F1 — Angle mort de détection ⬜

À écrire dans `FONCTIONNALITES_OSIRION.md` : **une personne allongée n'est pas détectée**, même au
plancher de confiance de 0,10. Constaté sur la caméra 92, où un agent dort sur une natte au sol.
Sans conséquence sur la campagne 1 (la natte est hors zone, vérifié par remplissage du polygone),
mais **un agent qui se repose dans une zone produira un faux poste vacant**. Cette limite doit être
connue de l'exploitant : l'alerte met en cause une personne.

### F2 — Prérequis d'exploitation ⬜

Trois éléments échappent au périmètre du logiciel et doivent figurer comme prérequis contractuels,
pas comme défauts à corriger :

1. **Disponibilité de la passerelle HikCentral** — 44 902 refus de service sur la campagne 1.
2. **Qualité du lien internet** du site d'hébergement — c'est la cause commune des 502 HikCentral
   et des échecs DNS sur le serveur de messagerie.
3. **Matériel cible** — la campagne 1 a tourné sur un ordinateur portable (12 cœurs, 14 Go,
   GPU 6 Go) avec 15 relais de transcodage sur processeur. Les chiffres de performance ne sont
   pas transposables ; définir la cible réelle avant tout engagement de capacité.

---

## Lot G — Instrumentation de la campagne 2

À faire une fois A à E terminés, avant de lancer.

1. **Clôturer la campagne 1.** `observation_runs/eval_20260827T145943Z/manifest.json` porte
   encore `"status": "running"` et `ended_at_utc: null`. La clôturer sur son vrai cutoff
   (`2026-09-03 11:24 UTC`) et archiver le dossier.
2. **Étendre les métriques** avec les champs du lot A4 et l'espace disque du lot E2.
3. **Fixer la durée** de la campagne 2 et la vérifier contre l'espace disque disponible **avant**
   de lancer, pas pendant.
4. **Consigner la configuration de départ** — le mécanisme `configuration_start.json` existe déjà
   et a bien fonctionné ; il permettra de prouver que les plannings du lot C étaient en place.

---

## Ce qui reste à faire

Classé par ce qui bloque réellement la relance de la campagne 2.

### Bloquant — et qui n'attend que vous

**C — Horaires et fuseaux.** Le seul point que personne d'autre ne peut trancher. Trois questions,
dans l'ordre : mesure-t-on la présence pendant les heures d'ouverture **réelles** ou en continu ?
Quelles sont ces heures, agence par agence, pauses comprises ? Et les postes de type magasin — la
caméra 106 « RETRAIT MAGASIN » notamment — doivent-ils être surveillés comme des guichets
(recommandation : **non**) ? Une fois ces réponses obtenues, C1 à C3 sont mécaniques : créer quatre
régimes, rattacher les neuf zones, saisir les plages.

**E3 — Archivage de la campagne 1.** Le disque est remonté à **20 Go libres** et la rétention
automatique protège désormais de la saturation silencieuse, donc l'urgence est retombée. Reste à
décider quoi archiver avant de purger. ⚠️ Ne jamais purger les données de la campagne 1 sans les
avoir archivées : elles sont la référence de comparaison de la campagne 2.

**Configuration UI — canal de repli.** À saisir dans Paramètres → Notifications. Sans webhook, la
file de reprise fonctionne mais sur un canal unique : un incident de messagerie prolongé épuisera
les cinq tentatives. C'est la mesure la plus rentable du lot B, et elle ne demande pas de code.

### Bloquant — et faisable sans vous

**B2 — Rendre visible une alerte non délivrée.** Les données sont en base (`notify_attempts`,
`notify_last_error`, `notify_next_retry_at`) et déjà exposées par `alerts_routes`. Il reste à
afficher l'état dans l'écran Alertes. Aujourd'hui une alerte perdue est indistinguable d'une alerte
livrée.

**D2 — Exclure les épisodes tronqués des agrégats.** `presence_data_quality` vaut désormais
`truncated` sur les épisodes clos par une panne. Il reste à les sortir des durées d'absence
affichées par défaut, en les proposant en option. ⚠️ Cela **change des chiffres déjà affichés** :
sur la campagne 1, le cumul passerait de 31,8 h à 14,5 h. À signaler avant de l'appliquer.

**G — Instrumentation.** Clôturer le manifeste de la campagne 1 (`status` est resté à `running`,
`ended_at_utc` à `null` ; vrai cutoff `2026-09-03 11:24 UTC`), puis fixer la durée de la campagne 2
et la vérifier contre l'espace libre **avant** de lancer.

### Non bloquant

**F1 — Angle mort de détection.** Documenter dans `FONCTIONNALITES_OSIRION.md` qu'une personne
**allongée** n'est pas détectée, même au plancher de 0,10. Sans effet sur la campagne 1 (vérifié :
la personne observée était hors zone), mais un agent qui se repose *dans* une zone produira un faux
poste vacant. À connaître de l'exploitant : l'alerte met en cause une personne.

**F2 — Prérequis d'exploitation.** Consigner comme prérequis contractuels, non comme défauts :
disponibilité de la passerelle HikCentral, qualité du lien internet du site, et définition du
matériel cible (la campagne 1 a tourné sur un portable 12 cœurs / 14 Go / GPU 6 Go avec 15 relais
de transcodage sur processeur — ces chiffres ne se transposent pas).

### Devenu sans objet

**La décision de terrain sur cam24.** Son échec systématique (100 % de timeouts) venait de la
relance permanente, pas d'un défaut propre. Depuis `closeAfter` à 180 s, elle est à 0 timeout comme
les autres. Aucune intervention sur site n'est nécessaire.

---

## Porte de contrôle — à passer avant toute relance

Chaque ligne doit être **vérifiée par sa commande**, pas supposée. Une case non cochée bloque la
relance de la campagne longue.

### Chaîne vidéo

- [x] **Aucun chemin MediaMTX ne survit sans URL valide** (A1) — vérifié en production le
      2026-09-04 : 14 chemins hérités supprimés au démarrage, et couvert par
      `test_stream_resilience.PathReapingTests`
- [x] **Le disjoncteur du résolveur s'ouvre** sous panne de la passerelle (A2) — couvert par
      `ResolverBreakerTests`
- [x] **Les métriques distinguent** panne passerelle et panne caméra (A4) — bloc `ingest`
- [x] **Un réglage modifié se propage aux chemins existants** — couvert par
      `test_un_reglage_modifie_est_propage_aux_chemins_existants`
- [x] **Taux d'échec des relais sous 5 %** — **0,0 %** mesuré sur 24 min le 2026-09-04
      (12 démarrages, 0 timeout)

> ⚠️ **Évaluer ce taux par caméra, pas en moyenne.** À l'étape intermédiaire, une seule caméra
> défaillante portait la moyenne à 25 % alors que les quatorze autres étaient à 4,5 %. Une moyenne
> masque un appareil en panne autant qu'elle masque un parc sain.

À rejouer sur le test de fumée avant la campagne :

```bash
python3 - <<'PY'
import re, collections, datetime
START = datetime.datetime.now() - datetime.timedelta(hours=2)
pat = re.compile(r'^(\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2})')
c = collections.Counter()
for line in open("logs-mediamtx/mediamtx.log", errors="replace"):
    m = pat.match(line)
    if not m or datetime.datetime.strptime(m.group(1), "%Y/%m/%d %H:%M:%S") < START:
        continue
    if "runOnDemand command started" in line: c["start"] += 1
    if "runOnDemand command stopped: timed out" in line: c["timeout"] += 1
t = 100 * c["timeout"] / c["start"] if c["start"] else 0
print(f"demarrages={c['start']} timeouts={c['timeout']} echec={t:.1f}%  ->  {'OK' if t < 5 else 'BLOQUANT'}")
PY
```

> **Sortie de référence au 2026-09-03, état avant corrections :**
> `demarrages=68 timeouts=46 echec=67.6%  ->  BLOQUANT`
>
> Mesuré sur les 2 heures suivant le redémarrage de la pile, sans aucune modification de code :
> le défaut est toujours actif. C'est la valeur à faire passer sous 5 %.

- [ ] **Aucune heure à zéro caméra** pendant le test de fumée, hors coupure de courant avérée

### Alertes

- [ ] **Webhook de repli configuré** — Paramètres → Notifications, testé par le bouton d'essai (B1.1)
- [x] **File de reprise opérationnelle** (B1.3) — thread `notification_retry` actif, 1/5/15/30 min
      puis abandon explicite ; couvert par `app/tests/test_notification_retry.py` (7 tests).
      Reste à valider en conditions réelles : couper le SMTP 5 min et vérifier qu'aucune alerte
      n'est définitivement perdue
- [ ] **Les alertes non délivrées sont visibles** dans l'interface (B2)

### Métier

- [ ] **Décision prise et écrite** sur les heures d'ouverture et le périmètre des postes (Lot C)
- [ ] **Quatre régimes horaires créés**, un par pays, aux bons fuseaux IANA (C1)
- [ ] **Les 9 zones rattachées** au bon régime, zone 16 qualifiée (C2)
- [ ] **Vérification en base :**

```bash
docker compose exec -T -w /app backend python - <<'PY'
import sys; sys.path.insert(0, "/app")
from sqlmodel import Session, select
from app.database import engine
from app.models.zones import Zone
from app.models.work_schedule import WorkSchedule
from app.models import camera_groups, users, events, alerts, cameras, rules, camera_status_event, notification_config, audit  # noqa

FULL_DAY = ["00:00", "00:00"]
ATTENDU = {2: "Africa/Lome", 3: "Africa/Lome", 4: "Africa/Porto-Novo", 5: "Africa/Porto-Novo",
           6: "Africa/Niamey", 9: "Africa/Niamey", 12: "Africa/Bamako", 13: "Africa/Bamako"}
# zone 16 volontairement absente : à qualifier (cf. C2)

def minutes(seg):
    a, b = seg
    h1, m1 = map(int, a.split(":")); h2, m2 = map(int, b.split(":"))
    d = (h2 * 60 + m2) - (h1 * 60 + m1)
    return 1440 if seg == FULL_DAY else (d if d > 0 else d + 1440)

with Session(engine) as s:
    sch = {w.id: w for w in s.exec(select(WorkSchedule)).all()}
    print(f"regimes horaires = {len(sch)}  (attendu : 4)")
    ko = 0
    for z in sorted(s.exec(select(Zone)).all(), key=lambda z: z.id):
        if z.kind != "presence":
            continue
        w = sch.get(z.work_schedule_id)
        pbs = []
        if not w:
            pbs.append("SANS REGIME"); hebdo = 0
        else:
            segs = w.segments or {}
            hebdo = sum(minutes(sg) for jour in segs.values() for sg in jour) / 60
            if any(sg == FULL_DAY for jour in segs.values() for sg in jour):
                pbs.append("PLAGE 24H")
            att = ATTENDU.get(z.id)
            if att is None:
                pbs.append("A QUALIFIER")
            elif w.timezone != att:
                pbs.append(f"FUSEAU {w.timezone} != {att}")
        if pbs:
            ko += 1
        print(f"  zone {z.id:>3} cam {z.camera_id:>4} {(w.name if w else '(aucun)'):<12} "
              f"{(w.timezone if w else ''):<19} {hebdo:5.0f} h/sem  "
              f"{'; '.join(pbs) if pbs else 'ok'}")
    ok = (ko == 0 and len(sch) >= 4)
    print("PORTE :", "OK" if ok else f"BLOQUANT ({ko} zone(s) en defaut, {len(sch)} regime(s))")
PY
```

<details>
<summary>Sortie de référence au 2026-09-03 — état <strong>avant</strong> corrections</summary>

```
regimes horaires = 1  (attendu : 4)
  zone   2 cam   65 UTC+1        Africa/Niamey         167 h/sem  PLAGE 24H; FUSEAU Africa/Niamey != Africa/Lome
  zone   3 cam   93 UTC+1        Africa/Niamey         167 h/sem  PLAGE 24H; FUSEAU Africa/Niamey != Africa/Lome
  zone   4 cam   92 UTC+1        Africa/Niamey         167 h/sem  PLAGE 24H; FUSEAU Africa/Niamey != Africa/Porto-Novo
  zone   5 cam  106 UTC+1        Africa/Niamey         167 h/sem  PLAGE 24H; FUSEAU Africa/Niamey != Africa/Porto-Novo
  zone   6 cam   24 UTC+1        Africa/Niamey         167 h/sem  PLAGE 24H
  zone   9 cam   62 UTC+1        Africa/Niamey         167 h/sem  PLAGE 24H
  zone  12 cam    9 UTC+1        Africa/Niamey         167 h/sem  PLAGE 24H; FUSEAU Africa/Niamey != Africa/Bamako
  zone  13 cam   10 UTC+1        Africa/Niamey         167 h/sem  PLAGE 24H; FUSEAU Africa/Niamey != Africa/Bamako
  zone  16 cam   89 UTC+1        Africa/Niamey         167 h/sem  PLAGE 24H; A QUALIFIER
PORTE : BLOQUANT (9 zone(s) en defaut, 1 regime(s))
```

**167 h sur 168** : le planning est ouvert en permanence, à une heure près (la coupure du
vendredi midi). C'est la mesure quantifiée du défaut décrit au lot C.

</details>

### Données

- [x] **`presence_data_quality` dérive du motif de clôture** (D1) — `truncated` sauf
      `presence_restored` ; couvert par `test_qualite_de_donnee_suit_le_motif_de_cloture`
- [ ] **Les agrégats excluent les épisodes tronqués** par défaut (D2)

### Exploitation

- [x] **Rétention automatique active** (E1) — `RETENTION_DAYS=30`, thread démarré au boot ;
      purge manuelle et automatique partagent la même implémentation
- [x] **Espace disque exposé et surveillé** (E2) — `GET /maintenance/disk` + log ERROR sous
      `RETENTION_MIN_FREE_GB` (10 Go). Relevé au 2026-09-04 : **20,1 Go libres** (77,5 % occupé)
- [ ] **Campagne 1 archivée** puis espace libéré (E3)
- [ ] **Au moins 40 Go libres** avant lancement :

```bash
df -h . | tail -1
du -sh observation_runs/ logs-mediamtx/
docker run --rm -v osirion_snapshots_data:/snap:ro alpine du -sh /snap
```

### Instrumentation

- [ ] **Manifeste de la campagne 1 clôturé** (G1)
- [ ] **Durée de la campagne 2 fixée** et compatible avec l'espace libre (G3)

---

## Protocole de relance

**Ne pas enchaîner directement sur une campagne de 7 jours.** La campagne 1 a coûté une semaine
pour découvrir un défaut visible en deux heures.

### Étape 1 — Test de fumée, 2 heures, en mode normal

```bash
cd /home/nevlana/Documents/Osirion
docker compose up -d
```

Laisser tourner 2 heures, puis passer les contrôles « chaîne vidéo » de la porte de contrôle.
**Si le taux d'échec des relais dépasse 5 %, s'arrêter et corriger** — inutile d'aller plus loin.

### Étape 2 — Canari, 24 heures, en mode campagne

```bash
RUN_ID=canari_$(date -u +%Y%m%dT%H%M%SZ)
OBSERVATION_RUN_ID="$RUN_ID" docker compose \
  -f docker-compose.yml -f docker-compose.observation.yml up -d --force-recreate
docker compose -f docker-compose.yml -f docker-compose.observation.yml exec -T \
  backend python /app/scripts/observation_bundle.py start --run-id "$RUN_ID"
```

À l'issue des 24 h, vérifier : disponibilité vidéo, croissance disque réelle par jour, cohérence
des alertes avec les nouveaux plannings, et absence de notification perdue.

### Étape 3 — Campagne 2

Même commande avec `RUN_ID=eval_…`, sur la durée fixée en G3. Reprendre la ligne de base
(`last_event_id`, `last_alert_id`, `last_camera_status_id`) au démarrage, comme pour la campagne 1.

---

## Ce que ce plan ne corrige pas

Volontairement hors périmètre, à porter comme risques acceptés ou prérequis :

- **La stabilité de la passerelle HikCentral** — le lot A rend Osirion *résilient* à ses pannes,
  il ne les supprime pas.
- **La qualité du lien internet** du site.
- **La détection des personnes allongées** — limite du modèle, documentée en F1, non corrigeable
  sans changer de modèle ou ajouter une classe.
- **Le dimensionnement matériel** — décision d'infrastructure, pas de développement.

---

## Journal d'avancement

| Lot | État | Date | Note |
|---|---|---|---|
| A1 | **Fait** | 2026-09-04 | Chemin supprimé si URL non résolue **et** capture morte. Garde ajoutée : un flux encore vivant n'est jamais coupé. |
| A2 | **Fait** | 2026-09-04 | Disjoncteur partagé dans `hik_stream_resolver` ; `refresh=True` neutralisé dès le 1<sup>er</sup> échec. |
| A3 | **Remplacé** | 2026-09-04 | La résolution groupée était **impossible** (`previewURLs` ne prend qu'une caméra). Remplacé par `closeAfter` 180 s + comparaison de configuration complète — **c'est le correctif décisif : 0 % d'échec, 14/15 caméras**. |
| A4 | **Fait** | 2026-09-04 | Bloc `ingest` dans `system_sample` (compteurs + état du disjoncteur). |
| B1 | **Fait** | 2026-09-04 | Champs de reprise sur `Alert` + migration `64b322f7fbe8` + thread `notification_retry` (1/5/15/30 min, abandon à 5). Le canal de repli reste à **configurer dans l'UI**. |
| B2 | À faire | | Affichage « non délivrée » dans l'écran Alertes (données déjà en base). |
| C — décision | ⛔ **Bloqué** | | Arbitrage métier requis — **bloque C1 à C3**, seul point qu'aucun développement ne peut lever |
| C1 | À faire | | 4 régimes : Niger `Africa/Niamey`, Bénin `Africa/Porto-Novo`, Mali `Africa/Bamako`, Togo `Africa/Lome` |
| C2 | À faire | | Rattacher les 9 zones ; **zone 16 (cam 89) sans localisation → à qualifier** |
| C3 | À faire | | Remplacer `[["00:00","00:00"]]` par les plages réelles ; garder `absence_tolerance_s=900` |
| D1 | **Fait** | 2026-09-04 | `presence_data_quality` dérive du motif : `truncated` sauf `presence_restored`. Test de non-régression ajouté. |
| D2 | À faire | | Exclure les épisodes `truncated` des agrégats métier par défaut. |
| E1 | **Fait** | 2026-09-04 | `retention_scheduler` (thread), `RETENTION_DAYS=30` ; purge manuelle et automatique partagent la même implémentation. |
| E2 | **Fait** | 2026-09-04 | `GET /maintenance/disk` + log ERROR sous `RETENTION_MIN_FREE_GB`. |
| E3 | À faire | | Décision d'archivage — **demande un arbitrage**, non traité. |
| F1 | À faire | | Angle mort « personne allongée » → `FONCTIONNALITES_OSIRION.md` |
| F2 | À faire | | Prérequis d'exploitation : passerelle, lien internet, matériel cible |
| G | À faire | | Clôturer le manifeste de la campagne 1 ; fixer la durée de la campagne 2 |
| cam24 | **Sans objet** | 2026-09-04 | L'échec venait de la relance permanente, pas de la caméra. 0 timeout depuis `closeAfter`. Aucune intervention sur site. |

### État du dépôt

Branche `sentinel-stable`. **Rien n'est commité** — tout est dans l'arbre de travail, en attente de
relecture. La migration `64b322f7fbe8`, elle, est **déjà appliquée en base**.

```
 M app/config.py                          M config/settings.py
 M app/main.py                            M core/event_engine.py
 M app/models/alerts.py                   M core/surveillance_system.py
 M app/routes/maintenance_routes.py       M core/tests/test_presence_schedule.py
 M app/services/rule_engine.py            M services/hik_stream_resolver.py
                                          M services/mediamtx_path_service.py
?? alembic/versions/64b322f7fbe8_alert_notify_retry.py
?? app/services/notification_retry.py    ?? core/tests/test_stream_resilience.py
?? app/services/retention_scheduler.py   ?? PLAN_CORRECTIONS_AVANT_CAMPAGNE_2.md
?? app/tests/test_notification_retry.py  ?? audit_vacances_2026-09-03/
```

Pour revenir en arrière sur le code : `git checkout -- <fichier>`. Pour annuler la migration :
`docker compose exec -T -w /app backend alembic downgrade f1a2b3c4d5e6`.

---

*Établi le 2026-09-03 à partir de la campagne `eval_20260827T145943Z`, cutoff
`2026-09-03 11:30:00 UTC`, puis tenu à jour au fil des corrections. Tous les chiffres cités sont
vérifiés sur la base de production en lecture seule, les métriques système, les journaux MediaMTX
et les journaux du moteur d'analyse — jamais estimés.*

*Dernière mise à jour : 2026-09-04, après le lot A complet, B1, D1, E1 et E2.*

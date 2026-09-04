# Relève — analyse de la campagne d'observation Osirion

## Mission

Poursuivre l'analyse de la campagne longue durée lancée pour évaluer le niveau de maturité production d'Osirion, en tenant compte des nombreuses coupures de courant survenues pendant la semaine.

L'utilisateur veut à terme une conclusion exploitable sur :

- la fiabilité de la détection de présence et des alertes de poste vacant ;
- la disponibilité des caméras et l'effet réel des coupures ;
- les performances du Core/GPU ;
- l'intégrité des événements, alertes et images ;
- les corrections nécessaires avant une mise en production.

Ne pas purger les données, ne pas arrêter la campagne et ne pas écraser les images. L'analyse effectuée jusqu'ici est en lecture seule, hormis la création des planches de contrôle et d'un script de rendu.

## Dépôt et état Git

- Racine : `/home/nevlana/Documents/Osirion`
- Branche : `sentinel-stable`
- HEAD : `7f98fec fix: initialiser le manifeste après les métriques`
- État distant au dernier contrôle : branche locale en avance d'un commit sur `origin/sentinel-stable`.
- L'utilisateur avait poussé le commit précédent, mais `7f98fec` n'était pas encore sur le distant au dernier contrôle.
- Fichier non suivi créé uniquement pour l'audit visuel :
  `Osirion-backend-main/Osirion-backend-main/scripts/render_vacancy_audit.py`
- Ne pas supprimer ou commiter ce fichier sans décider s'il doit devenir un outil permanent.

Commits fonctionnels pertinents :

- `af55015 feat: fiabiliser le suivi de présence des agents`
- `1a1d4d0 feat: ajouter une campagne d'observation production`
- `7f98fec fix: initialiser le manifeste après les métriques`

## Campagne analysée

- Run ID : `eval_20260827T145943Z`
- Dossier : `/home/nevlana/Documents/Osirion/observation_runs/eval_20260827T145943Z`
- Manifeste : `observation_runs/eval_20260827T145943Z/manifest.json`
- Début officiel UTC : `2026-08-27T15:06:08.716464+00:00`
- Début Niamey : `2026-08-27 16:06:08`
- Statut du manifeste au dernier contrôle : `running`
- Cutoff figé utilisé pour les chiffres ci-dessous : `2026-09-03 10:58:45.451754 UTC`, soit `11:58:45` à Niamey.
- Baselines du manifeste :
  - dernier événement avant campagne : `314176`
  - dernière alerte avant campagne : `0`
  - dernier statut caméra avant campagne : `24571`
- Audit visuel de présence : une image toutes les 120 secondes par zone pendant le planning.
- Métriques système : toutes les 30 secondes.

La campagne continuant à tourner, toute requête reprise ultérieurement doit soit conserver ce cutoff pour reproduire les chiffres, soit annoncer explicitement un nouveau cutoff.

## Volumétrie et espace disque au cutoff

- Snapshots : environ `7,9 Gio`.
- Espace disque libre : environ `14 Gio`.
- Partition : environ `88 %` occupée.
- Dossier de campagne (métriques et configuration, hors snapshots) : environ `41 Mio`.
- `metrics.jsonl` : `42 416 109` octets au contrôle le plus récent.

L'espace restant est un risque si la campagne continue longtemps avec l'audit toutes les deux minutes. Recontrôler avec `df -h` avant toute prolongation importante. Ne pas lancer un export intégral des images sans estimer sa taille : cela dupliquerait plusieurs gigaoctets.

## Résultats déjà établis

### 1. Événements et images

Entre la baseline et le cutoff : `242 578` événements.

| Type | Événements | Avec image |
|---|---:|---:|
| `ZONE_OCCUPANCY_CHANGED` | 133 096 | 4 855 |
| `ZONE_DWELL` | 94 278 | 0 |
| `PRESENCE_AUDIT_SAMPLE` | 12 532 | 12 532 |
| `CROWD_DETECTED` | 2 524 | 2 524 |
| `POST_ABSENCE` | 74 | 74 |
| `POST_VACANT` | 74 | 74 |

Répartition journalière :

| Jour UTC | Événements | Images | Audits présence | Postes vacants |
|---|---:|---:|---:|---:|
| 27 août | 35 180 | 2 548 | 1 671 | 1 |
| 28 août | 50 943 | 3 528 | 2 086 | 0 |
| 29–30 août | 0 | 0 | 0 | 0 |
| 31 août | 34 300 | 2 538 | 1 659 | 1 |
| 1 septembre | 72 294 | 5 867 | 3 451 | 23 |
| 2 septembre | 32 318 | 3 745 | 2 523 | 25 |
| 3 septembre, partiel | 17 543 | 1 833 | 1 142 | 24 |

Contrôles d'intégrité déjà passés :

- UID d'événement dupliqué : `0`
- alertes sans événement lié : `0`
- clôtures d'absence sans ouverture correspondante : `0`
- les 74 événements `POST_VACANT` ont une image ;
- les 74 événements `POST_ABSENCE` de clôture ont une image ;
- les 74 épisodes sont appariés ouverture/clôture.

### 2. Échantillons d'audit de présence

| Caméra / zone | Total | Occupé | Confirmation | Pending | Vacant |
|---|---:|---:|---:|---:|---:|
| 9 — PR Bamako | 1 083 | 591 | 199 | 275 | 18 |
| 10 — PR Bamako | 1 099 | 738 | 149 | 211 | 1 |
| 24 — PR Diffa | 681 | 359 | 122 | 192 | 8 |
| 62 — PR Diffa guichet | 1 668 | 1 374 | 142 | 139 | 13 |
| 65 — PR Guichet Lomé | 1 550 | 813 | 231 | 445 | 61 |
| 89 — PR | 1 508 | 934 | 207 | 352 | 15 |
| 92 — PR Messagerie Cotonou | 1 686 | 1 279 | 128 | 216 | 63 |
| 93 — PR Messagerie Lomé | 1 558 | 1 018 | 93 | 388 | 59 |
| 106 — PR Retrait Cotonou | 1 699 | 675 | 482 | 464 | 78 |

Il n'existe pas d'échantillon `unavailable` quand aucune frame n'arrive. C'est un choix de conception actuel : les indisponibilités doivent être reconstruites depuis les statuts caméra et les métriques, pas depuis les audits visuels.

### 3. Épisodes d'absence

Total cumulé des 74 épisodes : environ `1 905 minutes`, soit `31 h 45 min`.

| Caméra / zone | Épisodes | Total min | Moyenne | Minimum | Maximum |
|---|---:|---:|---:|---:|---:|
| 65 — Guichet Lomé | 17 | 408,3 | 24,0 | 16,3 | 62,4 |
| 106 — Retrait Cotonou | 16 | 483,9 | 30,2 | 15,6 | 75,9 |
| 93 — Messagerie Lomé | 14 | 332,6 | 23,8 | 15,2 | 41,7 |
| 9 — Bamako | 8 | 161,4 | 20,2 | 15,7 | 30,8 |
| 92 — Messagerie Cotonou | 7 | 235,7 | 33,7 | 17,9 | 73,0 |
| 62 — Diffa guichet | 5 | 118,5 | 23,7 | 16,0 | 32,9 |
| 89 — PR | 3 | 80,4 | 26,8 | 16,2 | 39,0 |
| 24 — Diffa | 2 | 49,2 | 24,6 | 21,3 | 27,8 |
| 10 — Bamako | 2 | 35,1 | 17,5 | 15,7 | 19,4 |

Raisons de clôture :

- `camera_unavailable` : `44` épisodes, soit `59,5 %` ;
- `presence_restored` : `30` épisodes, soit `40,5 %`.

Interprétation : la majorité des absences ouvertes n'ont pas été clôturées par le retour visible d'un agent, mais par la perte du flux caméra. Le système évite ainsi de gonfler indéfiniment le temps d'absence, mais les données métier sont fortement affectées par l'instabilité vidéo.

### 4. Alertes et règles

- Alertes créées : `557`
- Alertes avec image : `557`
- Alertes liées à un événement : `557`
- Alertes avec `notified_at` renseigné : `509`
- Alertes non marquées comme notifiées : `48`

Les 74 `POST_VACANT` ont chacun produit une alerte. Il reste à expliquer les 48 notifications manquantes par type d'alerte et motif d'échec.

Règles actives observées :

- règle 4, « Poste d'agent vacant », trigger `POST_VACANT`, cooldown 900 s ;
- règle 5, « Saturation file d'attente », trigger `CROWD_DETECTED`, cooldown 120 s.

Le compteur cumulé des règles et le total des alertes diffèrent légèrement ; vérifier si cela provient de règles supprimées/modifiées ou de données antérieures.

### 5. Coupures de courant et sessions Core

Analyse de `metrics.jsonl` :

- lignes JSON invalides : `0`
- durée murale entre début et cutoff : `163,88 h`
- durée réellement observée par les métriques : `92,72 h`
- couverture murale : `56,58 %`

Segments observés, en heure locale Niamey :

1. 27 août 16:06 → 23:11 : `7,08 h`
2. 28 août 09:42 → 09:44 : `0,03 h`
3. 28 août 09:45 → 21:15 : `11,50 h`
4. 28 août 22:23 → 22:26 : `0,05 h`
5. 31 août 09:55 → 3 septembre 11:58 : `74,06 h` continues

Gaps majeurs :

- 27 août 23:10 → 28 août 09:42 : `10,53 h`
- microcoupure/redémarrage d'environ `1,78 min`
- 28 août 21:15 → 22:23 : `1,14 h`
- 28 août 22:25 → 31 août 09:55 : `59,49 h`

Conclusion établie : les coupures sont clairement visibles, mais il existe tout de même une fenêtre continue très utile de 74 heures pour évaluer le système indépendamment des grandes coupures du serveur.

Script temporaire utilisé pour ce calcul : `/tmp/analyze_osirion_metrics.py`. Il peut disparaître après redémarrage ; conserver les résultats ci-dessus ou le recopier proprement si nécessaire.

### 6. Disponibilité des caméras

Sur tous les échantillons où le Core était actif :

- caméras en ligne : minimum `0`, médiane `10`, p95 `14`, maximum `15`.

Sur la fenêtre continue de 74 h :

- médiane : seulement `9` caméras en ligne ;
- p05 : `0` ;
- maximum : `15`.

Pourcentage en ligne pendant cette fenêtre continue :

| Caméra | % en ligne | Caméra | % en ligne |
|---:|---:|---:|---:|
| 9 | 24,35 % | 10 | 24,50 % |
| 13 | 24,73 % | 24 | 23,74 % |
| 28 | 51,43 % | 41 | 51,47 % |
| 62 | 50,58 % | 65 | 48,24 % |
| 74 | 51,55 % | 89 | 46,42 % |
| 92 | 50,65 % | 93 | 48,45 % |
| 104 | 29,44 % | 106 | 51,40 % |
| 109 | 50,99 % |  |  |

Ce résultat est le principal blocage production découvert. Ces faibles taux sont mesurés pendant que le Core tourne sans interruption pendant 74 h : les grandes coupures nationales ne suffisent donc pas à les expliquer. La couche de transport/reconnexion des flux est probablement le problème dominant.

Les transitions d'état sont extrêmement fréquentes :

| Caméra | Connecting | Offline | Online | Stalled | Total |
|---:|---:|---:|---:|---:|---:|
| 9 | 228 | 10 | 247 | 79 | 564 |
| 10 | 240 | 10 | 271 | 118 | 639 |
| 13 | 263 | 10 | 278 | 94 | 645 |
| 24 | 149 | 56 | 158 | 64 | 427 |
| 28 | 228 | 17 | 264 | 113 | 622 |
| 41 | 174 | 19 | 219 | 100 | 512 |
| 62 | 184 | 16 | 220 | 91 | 511 |
| 65 | 256 | 26 | 287 | 120 | 689 |
| 74 | 225 | 15 | 253 | 99 | 592 |
| 89 | 276 | 24 | 314 | 146 | 760 |
| 92 | 192 | 19 | 222 | 98 | 531 |
| 93 | 249 | 27 | 289 | 124 | 689 |
| 104 | 66 | 11 | 75 | 29 | 181 |
| 106 | 194 | 18 | 228 | 98 | 538 |
| 109 | 173 | 16 | 207 | 87 | 483 |

Le prochain agent doit corréler les états `stalled`, `connecting` et les logs Core pour identifier si les causes sont RTSP, timeout, watchdog, réseau local, décodage ou logique de reconnexion.

### 7. Performance Core/GPU

Mesures prises uniquement lorsque les caméras sont en ligne :

- FPS traité p05 : `2,52`
- FPS traité médian : `4,79`
- FPS traité p95 : `7,82`
- métrique p95 détection, médiane des échantillons : `252,35 ms`
- métrique p95 détection, p95 des échantillons : `530,16 ms`
- métrique p95 frame, médiane des échantillons : `264,60 ms`
- métrique p95 frame, p95 des échantillons : `551,75 ms`

GPU :

- utilisation médiane `19 %`, p95 `44 %` ;
- mémoire médiane et p95 `20,3 %` ;
- température médiane `60 °C`, p95 `65 °C`, maximum `70 °C`.

Conclusion provisoire : le GPU n'est pas saturé. Les performances sont modestes mais le problème le plus grave est la disponibilité des flux, pas la capacité GPU.

## Audit visuel des alertes de poste vacant

Les 74 images `POST_VACANT` ont été assemblées en cinq planches avec le polygone actuel superposé :

- `observation_runs/eval_20260827T145943Z/analysis/vacancies_01.jpg`
- `observation_runs/eval_20260827T145943Z/analysis/vacancies_02.jpg`
- `observation_runs/eval_20260827T145943Z/analysis/vacancies_03.jpg`
- `observation_runs/eval_20260827T145943Z/analysis/vacancies_04.jpg`
- `observation_runs/eval_20260827T145943Z/analysis/vacancies_05.jpg`

Le script de génération est le fichier non suivi mentionné dans l'état Git. Il se lance normalement depuis le conteneur backend :

```bash
docker compose exec backend python scripts/render_vacancy_audit.py
```

Constat prudent après inspection des planches :

- la majorité des zones semblent réellement vides ;
- plusieurs images montrent des personnes hors du polygone, ce qui ne constitue pas un faux positif d'absence ;
- une série concentrée sur la caméra 106 paraît ambiguë : des personnes sont visibles près du bureau et pourraient se trouver dans le polygone ;
- il faut examiner ces images en résolution originale et utiliser la géométrie de la boîte de détection/du point d'ancrage avant de conclure ;
- l'utilisateur a déjà corrigé une précédente lecture visuelle : une personne visible au fond n'était pas dans le polygone. Ne pas répéter cette erreur.

IDs suspects à vérifier en priorité, sans les qualifier encore de faux positifs :

`436178`, `438209`, `441245`, `448072`, `504874`, `507264`, `508064`, `509141`, `510445`, `539676`, `542196`, `543058`, `543672`, `546015`, `547982`.

Ils concernent principalement la caméra 106. Pour chacun :

1. ouvrir l'image originale ;
2. vérifier que le polygone au moment de l'événement est identique au polygone actuel ;
3. afficher les boîtes de personnes, leur confiance, le point d'ancrage utilisé et la relation point-dans-polygone ;
4. inspecter les audits des 10 à 20 minutes précédentes et suivantes ;
5. vérifier si l'alerte provient d'un vrai échec de détection, d'une personne partiellement hors zone, d'une occlusion ou d'une zone mal dessinée.

Attention : les planches utilisent les polygones actuels de la base. Comparer d'abord les zones de `configuration_start.json` avec les zones actuelles afin de garantir que l'overlay est historiquement valide.

## Anomalie de configuration probablement majeure

Une seule grille horaire a été observée pour les zones de présence : planning pratiquement 24 h/24, tous les jours, avec seulement une coupure le vendredi de 13 h à 14 h, fuseau UTC+1.

Cela semble incompatible avec les horaires réels d'agences et explique probablement de nombreuses alertes nocturnes où les postes sont naturellement vides. Les planches montrent de nombreuses alertes entre minuit et le début de matinée.

De plus, des agences de pays différents paraissent partager cette même grille UTC+1 :

- Diffa et Cotonou : UTC+1 cohérent ;
- Bamako et Lomé : normalement UTC+0, donc décalage probable d'une heure.

Ce point doit être confirmé en base et avec le besoin métier avant correction. Il faut quantifier les 74 `POST_VACANT` par heure locale et distinguer :

- alertes pendant les vraies heures ouvrées ;
- alertes hors heures ouvrées ;
- alertes touchées par un mauvais fuseau horaire.

Ne pas changer le planning sans validation utilisateur : le H24 a peut-être été configuré volontairement pour le test, même s'il rend les alertes métier peu représentatives.

## Investigations restantes, dans l'ordre recommandé

### Priorité 1 — Finaliser la vérité terrain des 74 alertes

- Comparer configuration de départ et configuration actuelle.
- Produire des images détaillées des IDs suspects, avec boîtes, ancres et polygones.
- Classer chaque alerte : vrai vacant, personne hors zone, personne dans zone non détectée, zone incorrecte, image ambiguë.
- Calculer précision apparente et taux d'images non concluantes.
- Séparer caméra 106 des autres caméras : elle concentre les ambiguïtés visuelles.

### Priorité 2 — Auditer les horaires et fuseaux

- Lire les tables de groupes/plannings/segments et les affectations de chaque zone.
- Produire un histogramme des `POST_VACANT` par heure locale et par pays.
- Vérifier si le test H24 était volontaire.
- Proposer au besoin un groupe par fuseau/pays et de vraies heures ouvrées avec pauses.

### Priorité 3 — Expliquer la disponibilité caméra catastrophique

- Compter et classifier les erreurs des logs Core par caméra et par motif.
- Corréler les transitions avec les gaps du serveur afin de distinguer :
  - coupure du serveur/site central ;
  - caméra ou agence inaccessible ;
  - flux bloqué/stalled ;
  - reconnexion qui échoue ou boucle ;
  - décodage/FFmpeg/OpenCV ;
  - saturation d'une file ou timeout interne.
- Mesurer la durée médiane en ligne, la durée médiane hors ligne et le nombre de flaps par heure.
- Vérifier si les groupes de caméras basculent ensemble, ce qui indiquerait une panne réseau/site plutôt qu'une panne caméra individuelle.

### Priorité 4 — Expliquer les 48 alertes non notifiées

- Répartir par `event_type`, règle, date et canal.
- Inspecter statut, raison d'échec, tentatives et logs de dispatch.
- Distinguer cooldown/suppression volontaire d'un échec technique.
- Vérifier que les 74 alertes de présence importantes ont bien été notifiées ou identifier celles qui ne l'ont pas été.

### Priorité 5 — Vérifier le stockage et la qualité des preuves

- Vérifier sur disque l'existence de toutes les images référencées, pas seulement la présence de l'URL en base.
- Détecter fichiers de taille nulle, illisibles ou hash identique anormalement répété.
- Mesurer la croissance quotidienne et estimer le nombre de jours avant saturation disque.
- Vérifier les rotations de logs et l'absence de pertes autour des redémarrages.

### Priorité 6 — Rapport de maturité production

Le rapport final doit donner un verdict clair par axe :

- détection et vérité terrain ;
- logique présence/absence ;
- alerting et notifications ;
- disponibilité vidéo ;
- performance ;
- intégrité/stockage ;
- exploitation et UX.

Verdict provisoire à ce stade : la logique d'appariement des absences et la conservation des preuves fonctionnent, et le GPU dispose de marge. En revanche, il est prématuré de déclarer le système prêt pour la production à cause de la très faible disponibilité des flux pendant une fenêtre où le Core était pourtant stable, ainsi que de la configuration horaire possiblement non représentative.

## Méthode de reprise technique

Les services sont définis dans :

- `/home/nevlana/Documents/Osirion/docker-compose.yml`
- `/home/nevlana/Documents/Osirion/docker-compose.observation.yml`

Contrôle initial recommandé :

```bash
cd /home/nevlana/Documents/Osirion
git status --short --branch
docker compose ps
df -h .
du -sh observation_runs/eval_20260827T145943Z
```

Pour les requêtes, privilégier une session Python/SQLModel dans le conteneur backend afin de réutiliser la configuration de base sans afficher de mot de passe :

```bash
docker compose exec backend python -c 'from app.database import engine; print(engine.url.render_as_string(hide_password=True))'
```

Fixer explicitement dans les requêtes :

- `Event.id > 314176`
- `CameraStatus.id > 24571`
- `timestamp <= 2026-09-03 10:58:45.451754+00:00` pour reproduire l'analyse actuelle.

Si l'objectif devient d'analyser la totalité de la campagne jusqu'à un nouveau moment, prendre d'abord un nouveau cutoff UTC, l'inscrire dans le rapport, puis recalculer tous les totaux de manière cohérente.

## Précautions

- Ne jamais supprimer les événements, alertes, snapshots ou métriques de cette campagne.
- Ne pas lancer de nettoyage Docker ou de volume.
- Ne pas exporter/coller les URLs RTSP ou les identifiants présents dans la configuration.
- Préserver les modifications utilisateur et les fichiers non liés dans le worktree.
- Ne pas confondre une personne visible dans l'image avec une personne géométriquement présente dans la zone.
- Ne pas attribuer toutes les pertes caméra aux coupures nationales : la fenêtre continue de 74 h démontre une instabilité supplémentaire.
- Ne pas interpréter les 31 h 45 d'absence cumulée comme une mesure métier fiable tant que le planning H24 et les clôtures `camera_unavailable` n'ont pas été séparés.

## Définition de terminé

La relève est terminée lorsque l'agent suivant fournit :

1. un classement visuel argumenté des 74 alertes de poste vacant ;
2. une analyse des horaires/fuseaux et des alertes nocturnes ;
3. une cause ou au minimum une classification solide des pertes de flux ;
4. l'explication des 48 notifications manquantes ;
5. un contrôle physique des images et une projection d'espace disque ;
6. un rapport final avec verdict production, risques classés et plan de corrections priorisé ;
7. aucune modification fonctionnelle sans accord de l'utilisateur après présentation des conclusions.

#!/usr/bin/env python3
"""Alimente les écrans de présentation avec un historique métier cohérent.

Le script ne modifie que la table ``event``. Il réutilise les caméras, groupes,
zones et lignes existants et ne crée volontairement aucune alerte : les données
servent le Cockpit, l'Analytique, le Journal d'événements et les Rapports sans
toucher à la configuration opérationnelle.

Exemples (depuis le conteneur backend) :

    python scripts/seed_presentation_data.py --dry-run
    python scripts/seed_presentation_data.py --days 180
    python scripts/seed_presentation_data.py --days 180 --refresh

Toutes les lignes portent ``meta.demo_seed = presentation_v1``. Une exécution
normale est donc idempotente ; ``--refresh`` remplace atomiquement le jeu de
démonstration précédent et le recale par rapport à la date courante.
"""

from __future__ import annotations

import argparse
import math
import random
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Iterable, Sequence

# Exécuté comme ``python scripts/...``, Python place /app/scripts (et non /app)
# dans sys.path. On ajoute explicitement la racine du backend pour rendre la
# commande identique sur l'hôte et dans le conteneur.
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import delete, func
from sqlalchemy.orm import selectinload
from sqlmodel import Session, select

from app.database import engine
from app.models.camera_groups import CameraGroup  # noqa: F401 - initialise le mapper
from app.models.cameras import Camera
from app.models.events import (
    EVENT_CROWD_DETECTED,
    EVENT_LINE_CROSSED,
    EVENT_ZONE_DWELL,
    EVENT_ZONE_OCCUPANCY_CHANGED,
    Event,
)
from app.models.zones import CountLine, Zone, ZONE_QUEUE


SEED_TAG = "presentation_v1"
DEFAULT_DAYS = 180  # couvre aussi la période précédente du filtre 90 jours
DEFAULT_RANDOM_SEED = 26_081_301

# Volume global moyen d'entrées par jour ouvré, ensuite réparti par site/caméra.
BASE_DAILY_ENTRIES = 330

# Les lundis et vendredis sont volontairement plus chargés. Le week-end reste
# visible dans les graphes, mais à un niveau cohérent avec des agences fermées.
WEEKDAY_FACTORS = (1.12, 1.02, 0.98, 1.06, 1.18, 0.20, 0.08)

# Profil horaire utilisé pour tirer les passages. Deux pics rendent les graphes,
# heatmaps et prévisions lisibles pendant une présentation.
ENTRY_HOURS = (
    (7, 0.02), (8, 0.07), (9, 0.13), (10, 0.15), (11, 0.12),
    (12, 0.06), (13, 0.05), (14, 0.10), (15, 0.12), (16, 0.09),
    (17, 0.06), (18, 0.02), (19, 0.01),
)
EXIT_HOURS = (
    (8, 0.02), (9, 0.04), (10, 0.07), (11, 0.09), (12, 0.12),
    (13, 0.08), (14, 0.07), (15, 0.10), (16, 0.12), (17, 0.14),
    (18, 0.10), (19, 0.04), (20, 0.01),
)

# Poids relatifs par agence. Ils s'appliquent au site entier : un site possédant
# plusieurs caméras ne gagne donc pas artificiellement du poids.
SITE_WEIGHTS = {
    "SIEGE": 1.55,
    "BAMAKO": 1.30,
    "ACCRA": 1.15,
    "DOSSO": 0.92,
    "INTERIEUR": 0.82,
    "EXTERIEUR": 0.55,
}

# Occupation relative au seuil/capacité de référence au fil de la journée.
OCCUPANCY_PROFILE = (
    (7, 30, 0.00),
    (8, 0, 0.08),
    (9, 0, 0.28),
    (10, 0, 0.52),
    (11, 0, 0.68),
    (12, 0, 0.42),
    (13, 0, 0.25),
    (14, 0, 0.48),
    (15, 0, 0.72),
    (16, 0, 0.58),
    (17, 0, 0.38),
    (18, 0, 0.24),
    (19, 0, 0.14),
    (20, 0, 0.05),
    (21, 0, 0.00),
)


@dataclass(frozen=True)
class CameraTarget:
    id: int
    name: str
    site: str
    share: float
    line_id: int | None
    line_name: str


@dataclass(frozen=True)
class ZoneTarget:
    id: int
    camera_id: int
    name: str
    kind: str
    threshold: int | None
    site: str


def _site_name(camera: Camera) -> str:
    if not camera.groups:
        return "Sans site"
    # Les groupes de type agence sont plus parlants que les anciens groupes
    # techniques « interieur/exterieur » quand plusieurs appartenances existent.
    names = sorted((g.name for g in camera.groups), key=lambda n: n.lower())
    preferred = [n for n in names if n.upper() not in {"INTERIEUR", "EXTERIEUR"}]
    return preferred[0] if preferred else names[0]


def _site_weight(site: str) -> float:
    return SITE_WEIGHTS.get(site.upper(), 0.72)


def _load_targets(session: Session) -> tuple[list[CameraTarget], list[ZoneTarget]]:
    cameras = list(
        session.exec(
            select(Camera)
            .where(Camera.is_active.is_(True))
            .options(selectinload(Camera.groups))
            .order_by(Camera.id)
        ).all()
    )
    if not cameras:
        raise RuntimeError(
            "Aucune caméra active : le jeu de présentation ne peut pas créer "
            "d'événements sans modifier la configuration."
        )

    lines = list(session.exec(select(CountLine).where(CountLine.is_active.is_(True))).all())
    lines_by_camera: dict[int, CountLine] = {}
    for line in lines:
        lines_by_camera.setdefault(line.camera_id, line)

    site_counts = Counter(_site_name(camera) for camera in cameras)
    raw_weights = [
        _site_weight(_site_name(camera)) / site_counts[_site_name(camera)]
        for camera in cameras
    ]
    total_weight = sum(raw_weights)
    camera_targets: list[CameraTarget] = []
    for camera, raw_weight in zip(cameras, raw_weights):
        line = lines_by_camera.get(camera.id)
        camera_targets.append(
            CameraTarget(
                id=camera.id,
                name=camera.cam_name,
                site=_site_name(camera),
                share=raw_weight / total_weight,
                line_id=line.id if line else None,
                line_name=line.name if line else "Flux visiteurs",
            )
        )

    camera_sites = {camera.id: _site_name(camera) for camera in cameras}
    zones = list(
        session.exec(select(Zone).where(Zone.is_active.is_(True)).order_by(Zone.id)).all()
    )
    if not zones:
        raise RuntimeError(
            "Aucune zone active : impossible d'alimenter l'occupation et les "
            "files sans modifier la configuration."
        )
    zone_targets = [
        ZoneTarget(
            id=zone.id,
            camera_id=zone.camera_id,
            name=zone.name,
            kind=zone.kind,
            threshold=zone.threshold,
            site=camera_sites.get(zone.camera_id, "Sans site"),
        )
        for zone in zones
    ]
    return camera_targets, zone_targets


def _allocate(total: int, shares: Sequence[float]) -> list[int]:
    """Répartit exactement ``total`` selon les parts, sans biais d'arrondi."""
    raw = [total * share for share in shares]
    allocated = [math.floor(value) for value in raw]
    remainder = total - sum(allocated)
    order = sorted(range(len(raw)), key=lambda i: raw[i] - allocated[i], reverse=True)
    for index in order[:remainder]:
        allocated[index] += 1
    return allocated


def _weighted_hour(rng: random.Random, profile: Sequence[tuple[int, float]]) -> int:
    cursor = rng.random()
    cumulative = 0.0
    for hour, weight in profile:
        cumulative += weight
        if cursor <= cumulative:
            return hour
    return profile[-1][0]


def _at_random_minute(day: date, hour: int, rng: random.Random) -> datetime:
    return datetime.combine(day, time(hour=hour)) + timedelta(
        minutes=rng.randrange(60), seconds=rng.randrange(60)
    )


def _event(
    *, camera_id: int, event_type: str, timestamp: datetime, meta: dict[str, Any],
    confidence: float | None = None,
) -> dict[str, Any]:
    return {
        "camera_id": camera_id,
        "event_type": event_type,
        "confidence": confidence,
        "snapshot_url": None,
        "meta": {**meta, "demo_seed": SEED_TAG},
        "timestamp": timestamp,
    }


def _passage_events(
    day: date,
    day_index: int,
    total_days: int,
    now: datetime,
    cameras: Sequence[CameraTarget],
    rng: random.Random,
) -> Iterable[dict[str, Any]]:
    trend = 0.91 + (0.12 * day_index / max(1, total_days - 1))
    noise = rng.uniform(0.94, 1.07)
    entries_total = round(BASE_DAILY_ENTRIES * WEEKDAY_FACTORS[day.weekday()] * trend * noise)
    exits_total = round(entries_total * rng.uniform(0.92, 0.98))

    entries_by_camera = _allocate(entries_total, [camera.share for camera in cameras])
    exits_by_camera = _allocate(exits_total, [camera.share for camera in cameras])
    for camera, entries, exits in zip(cameras, entries_by_camera, exits_by_camera):
        common_meta = {
            "line_id": camera.line_id,
            "line_name": camera.line_name,
            "site": camera.site,
        }
        for direction, count, profile in (
            ("in", entries, ENTRY_HOURS),
            ("out", exits, EXIT_HOURS),
        ):
            for _ in range(count):
                timestamp = _at_random_minute(day, _weighted_hour(rng, profile), rng)
                if timestamp > now:
                    continue
                yield _event(
                    camera_id=camera.id,
                    event_type=EVENT_LINE_CROSSED,
                    timestamp=timestamp,
                    confidence=round(rng.uniform(0.91, 0.99), 3),
                    meta={**common_meta, "direction": direction},
                )


def _zone_capacity(zone: ZoneTarget) -> int:
    if zone.threshold and zone.threshold > 0:
        return zone.threshold
    return 8 if zone.kind == ZONE_QUEUE else 22


def _current_profile_ratio(now: datetime) -> float:
    current_minutes = now.hour * 60 + now.minute
    previous = OCCUPANCY_PROFILE[0]
    for point in OCCUPANCY_PROFILE[1:]:
        point_minutes = point[0] * 60 + point[1]
        if current_minutes <= point_minutes:
            prev_minutes = previous[0] * 60 + previous[1]
            span = max(1, point_minutes - prev_minutes)
            progress = max(0.0, min(1.0, (current_minutes - prev_minutes) / span))
            return previous[2] + (point[2] - previous[2]) * progress
        previous = point
    return 0.0


def _occupancy_events(
    day: date,
    now: datetime,
    zones: Sequence[ZoneTarget],
    rng: random.Random,
) -> Iterable[dict[str, Any]]:
    day_factor = WEEKDAY_FACTORS[day.weekday()]
    for zone in zones:
        capacity = _zone_capacity(zone)
        for hour, minute, ratio in OCCUPANCY_PROFILE:
            timestamp = datetime.combine(day, time(hour=hour, minute=minute))
            if timestamp > now:
                continue
            # Une petite variation déterministe évite des courbes trop parfaites.
            varied = ratio * min(1.25, max(0.18, day_factor)) * rng.uniform(0.88, 1.12)
            count = max(0, round(capacity * varied))
            yield _event(
                camera_id=zone.camera_id,
                event_type=EVENT_ZONE_OCCUPANCY_CHANGED,
                timestamp=timestamp,
                confidence=round(rng.uniform(0.93, 0.99), 3),
                meta={
                    "zone_id": zone.id,
                    "zone_name": zone.name,
                    "kind": zone.kind,
                    "count": count,
                    "site": zone.site,
                },
            )

        # Le Cockpit s'appuie sur la dernière valeur des dernières 24 h. Ce point
        # recale proprement le jour courant sans inventer de timestamp futur.
        if day == now.date() and now >= datetime.combine(day, time(7, 30)):
            timestamp = now - timedelta(minutes=2)
            varied = _current_profile_ratio(now) * min(1.25, max(0.18, day_factor))
            count = max(0, round(capacity * varied))
            yield _event(
                camera_id=zone.camera_id,
                event_type=EVENT_ZONE_OCCUPANCY_CHANGED,
                timestamp=timestamp,
                confidence=0.97,
                meta={
                    "zone_id": zone.id,
                    "zone_name": zone.name,
                    "kind": zone.kind,
                    "count": count,
                    "site": zone.site,
                },
            )


def _wait_base_seconds(zone: ZoneTarget) -> float:
    by_site = {
        "DOSSO": 315.0,
        "SIEGE": 235.0,
        "BAMAKO": 205.0,
        "ACCRA": 185.0,
    }
    return by_site.get(zone.site.upper(), 170.0)


def _queue_events(
    day: date,
    now: datetime,
    queues: Sequence[ZoneTarget],
    rng: random.Random,
) -> Iterable[dict[str, Any]]:
    factor = WEEKDAY_FACTORS[day.weekday()]
    for zone in queues:
        samples = max(2, round(14 * factor))
        for _ in range(samples):
            hour = _weighted_hour(rng, ENTRY_HOURS)
            timestamp = _at_random_minute(day, hour, rng)
            if timestamp > now:
                continue
            peak_multiplier = 1.28 if hour in {9, 10, 11, 14, 15, 16} else 0.88
            wait = _wait_base_seconds(zone) * peak_multiplier * rng.lognormvariate(-0.05, 0.30)
            wait = round(min(900.0, max(35.0, wait)), 1)
            yield _event(
                camera_id=zone.camera_id,
                event_type=EVENT_ZONE_DWELL,
                timestamp=timestamp,
                confidence=round(rng.uniform(0.91, 0.99), 3),
                meta={
                    "zone_id": zone.id,
                    "zone_name": zone.name,
                    "kind": zone.kind,
                    "dwell_s": wait,
                    "site": zone.site,
                },
            )


def _crowd_events(
    day: date,
    now: datetime,
    zones: Sequence[ZoneTarget],
    rng: random.Random,
) -> Iterable[dict[str, Any]]:
    # Quelques incidents métier seulement : ils alimentent l'onglet Incidents,
    # mais aucune Alert n'est créée puisque l'insertion se fait directement en DB.
    probability = 0.52 * min(1.2, WEEKDAY_FACTORS[day.weekday()])
    if not zones or rng.random() > probability:
        return
    occurrences = 2 if day.weekday() == 4 and rng.random() < 0.30 else 1
    for _ in range(occurrences):
        zone = rng.choice(list(zones))
        hour = rng.choice((10, 11, 15, 16, 17))
        timestamp = _at_random_minute(day, hour, rng)
        if timestamp > now:
            continue
        threshold = zone.threshold or _zone_capacity(zone)
        yield _event(
            camera_id=zone.camera_id,
            event_type=EVENT_CROWD_DETECTED,
            timestamp=timestamp,
            confidence=round(rng.uniform(0.90, 0.98), 3),
            meta={
                "zone_id": zone.id,
                "zone_name": zone.name,
                "kind": zone.kind,
                "count": threshold + rng.randint(1, 4),
                "threshold": threshold,
                "site": zone.site,
            },
        )


def _day_events(
    day: date,
    day_index: int,
    days: int,
    now: datetime,
    cameras: Sequence[CameraTarget],
    zones: Sequence[ZoneTarget],
    rng: random.Random,
) -> list[dict[str, Any]]:
    queues = [zone for zone in zones if zone.kind == ZONE_QUEUE]
    rows = [
        *_passage_events(day, day_index, days, now, cameras, rng),
        *_occupancy_events(day, now, zones, rng),
        *_queue_events(day, now, queues, rng),
        *_crowd_events(day, now, zones, rng),
    ]
    rows.sort(key=lambda row: row["timestamp"])
    return rows


def _existing_seed_count(session: Session) -> int:
    marker = Event.meta["demo_seed"].as_string()
    statement = select(func.count()).select_from(Event).where(marker == SEED_TAG)
    return int(session.exec(statement).one())


def _delete_existing_seed(session: Session) -> int:
    marker = Event.meta["demo_seed"].as_string()
    result = session.execute(delete(Event).where(marker == SEED_TAG))
    return int(result.rowcount or 0)


def _chunks(rows: Sequence[dict[str, Any]], size: int) -> Iterable[Sequence[dict[str, Any]]]:
    for start in range(0, len(rows), size):
        yield rows[start:start + size]


def seed(args: argparse.Namespace) -> int:
    # Le schéma historique stocke des timestamps UTC naïfs ; on part d'un instant
    # UTC conscient puis on retire le tzinfo uniquement au bord de la DB.
    now = datetime.now(UTC).replace(tzinfo=None, microsecond=0)
    first_day = now.date() - timedelta(days=args.days - 1)
    rng = random.Random(args.random_seed)

    with Session(engine) as session:
        cameras, zones = _load_targets(session)
        queues = [zone for zone in zones if zone.kind == ZONE_QUEUE]
        existing = _existing_seed_count(session)

        print(
            f"Périmètre : {len(cameras)} caméra(s) active(s), "
            f"{len(zones)} zone(s), {len(queues)} file(s)."
        )
        print(f"Fenêtre : {first_day.isoformat()} → {now.date().isoformat()} ({args.days} jours).")

        if existing and not args.refresh:
            print(
                f"Jeu {SEED_TAG!r} déjà présent ({existing:,} événements). "
                "Utilisez --refresh pour le recaler sans doublons."
            )
            return 0

        if not queues:
            print(
                "Attention : aucune zone de type queue ; l'analytique des files "
                "restera vide (la configuration n'a pas été modifiée)."
            )

        totals: Counter[str] = Counter()
        inserted = 0
        deleted = 0
        try:
            if existing and args.refresh and not args.dry_run:
                deleted = _delete_existing_seed(session)

            for day_index in range(args.days):
                day = first_day + timedelta(days=day_index)
                rows = _day_events(
                    day, day_index, args.days, now, cameras, zones, rng
                )
                totals.update(row["event_type"] for row in rows)
                if args.dry_run:
                    continue
                for batch in _chunks(rows, args.batch_size):
                    session.execute(Event.__table__.insert(), list(batch))
                    inserted += len(batch)

            if args.dry_run:
                session.rollback()
            else:
                session.commit()
        except Exception:
            session.rollback()
            raise

    action = "Simulation" if args.dry_run else "Insertion"
    print(f"{action} terminée : {sum(totals.values()):,} événement(s).")
    for event_type, count in sorted(totals.items()):
        print(f"  - {event_type}: {count:,}")
    if deleted:
        print(f"Ancien jeu remplacé : {deleted:,} événement(s) supprimé(s).")
    if not args.dry_run:
        print(f"Événements insérés : {inserted:,}. Alertes créées : 0.")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Alimente les modules de présentation sans toucher à la configuration."
    )
    parser.add_argument(
        "--days",
        type=int,
        default=DEFAULT_DAYS,
        help=f"nombre de jours d'historique (défaut : {DEFAULT_DAYS})",
    )
    parser.add_argument(
        "--random-seed",
        type=int,
        default=DEFAULT_RANDOM_SEED,
        help="graine déterministe du scénario",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=2_000,
        help="taille des insertions SQL groupées",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="remplace le précédent jeu presentation_v1 dans une transaction",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="calcule le scénario et affiche les volumes sans écrire",
    )
    args = parser.parse_args()
    if not 7 <= args.days <= 365:
        parser.error("--days doit être compris entre 7 et 365")
    if not 100 <= args.batch_size <= 10_000:
        parser.error("--batch-size doit être compris entre 100 et 10000")
    return args


if __name__ == "__main__":
    raise SystemExit(seed(parse_args()))

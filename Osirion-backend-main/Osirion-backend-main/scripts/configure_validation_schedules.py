"""Configure les groupes horaires provisoires de la campagne de validation.

Idempotent : peut être relancé sans créer de doublons. Ces groupes H24 servent à
valider la chaîne technique ; ils ne constituent pas encore une vérité RH pour
les agences dont le statut principal et les horaires réels sont inconnus.
"""
from datetime import datetime
import sys
from pathlib import Path

from sqlmodel import Session, select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import engine
# Charge toutes les tables référencées afin que SQLAlchemy puisse ordonner les
# flush malgré les clés étrangères de Zone et Rule.
from app.models import (  # noqa: F401
    alerts, audit, camera_groups, camera_status_event, cameras, events,
    notification_config, rules, users, work_schedule, zones,
)
from app.models.rules import Rule
from app.models.work_schedule import WorkSchedule
from app.models.zones import Zone


SEGMENTS_H24 = {
    str(day): (
        [["00:00", "13:00"], ["14:00", "00:00"]]
        if day == 4 else [["00:00", "00:00"]]
    )
    for day in range(7)
}

GROUPS = {
    "Validation H24 — Niger": {
        "timezone": "Africa/Niamey", "zones": {6: 24, 9: 62},
    },
    "Validation H24 — Bénin": {
        "timezone": "Africa/Porto-Novo", "zones": {4: 92, 5: 106},
    },
    "Validation H24 — Mali": {
        "timezone": "Africa/Bamako", "zones": {12: 9, 13: 10},
    },
    "Validation H24 — Togo": {
        "timezone": "Africa/Lome", "zones": {2: 65, 3: 93, 16: 89},
    },
}

DESCRIPTION = (
    "PROVISOIRE — validation technique H24, pause prière vendredi 13h–14h. "
    "Ne pas interpréter les vacances nocturnes comme une mesure RH tant que le "
    "statut principal et les horaires réels de l’agence ne sont pas confirmés."
)


def main() -> None:
    with Session(engine) as session:
        zones = {z.id: z for z in session.exec(select(Zone)).all()}
        schedules = {
            s.name: s for s in session.exec(select(WorkSchedule)).all()
        }
        assigned = set()
        for name, spec in GROUPS.items():
            schedule = schedules.get(name)
            if schedule is None:
                schedule = WorkSchedule(
                    name=name,
                    description=DESCRIPTION,
                    timezone=spec["timezone"],
                    segments=SEGMENTS_H24,
                    absence_tolerance_s=900,
                    is_active=True,
                )
                session.add(schedule)
                session.flush()
            else:
                schedule.description = DESCRIPTION
                schedule.timezone = spec["timezone"]
                schedule.segments = SEGMENTS_H24
                schedule.absence_tolerance_s = 900
                schedule.is_active = True
                schedule.updated_at = datetime.utcnow()

            for zone_id, expected_camera in spec["zones"].items():
                zone = zones.get(zone_id)
                if zone is None or zone.kind != "presence":
                    raise RuntimeError(f"zone présence {zone_id} introuvable")
                if zone.camera_id != expected_camera:
                    raise RuntimeError(
                        f"zone {zone_id}: caméra {zone.camera_id}, attendu {expected_camera}"
                    )
                zone.work_schedule_id = schedule.id
                zone.updated_at = datetime.utcnow()
                session.add(zone)
                assigned.add(zone_id)

        unassigned = {
            z.id for z in zones.values() if z.kind == "presence"
        } - assigned
        if unassigned:
            raise RuntimeError(f"zones présence non qualifiées: {sorted(unassigned)}")

        # Une seule politique d'alerte globale évite qu'un nouveau groupe reste
        # silencieux faute de règle clonée. Le cooldown reste calculé par zone.
        for rule in session.exec(select(Rule).where(Rule.trigger == "POST_VACANT")).all():
            rule.work_schedule_id = None
            rule.updated_at = datetime.utcnow()
            session.add(rule)

        # L'ancien groupe reste en base pour l'historique, mais ne doit plus être
        # proposé pour de nouvelles affectations.
        for schedule in session.exec(select(WorkSchedule)).all():
            if schedule.name not in GROUPS and schedule.name == "UTC+1":
                schedule.is_active = False
                schedule.updated_at = datetime.utcnow()
                session.add(schedule)

        session.commit()
        for name, spec in GROUPS.items():
            print(f"{name}: {spec['timezone']} -> zones {sorted(spec['zones'])}")


if __name__ == "__main__":
    main()

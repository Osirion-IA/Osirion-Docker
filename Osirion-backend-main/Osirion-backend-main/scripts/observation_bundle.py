"""Démarre, suit et exporte une campagne d'observation Osirion.

Le bundle ne contient jamais les URL RTSP, clés HikCentral, mots de passe ou
variables d'environnement. Il rassemble uniquement les configurations métier,
les événements, alertes, transitions caméra et captures de la période.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from sqlalchemy import text
from sqlmodel import Session

# L'outil est volontairement exécutable directement depuis /app/scripts ; dans
# ce cas Python n'ajoute que ce sous-dossier au chemin d'import, pas /app.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import engine


ROOT = Path(os.getenv("OBSERVATION_ROOT", "/app/observation_runs"))
CURRENT = ROOT / "current.json"


def _json_value(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    return value


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=_json_value) + "\n",
        encoding="utf-8",
    )


def _write_jsonl(path: Path, rows: Iterable[dict]) -> int:
    count = 0
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, default=_json_value) + "\n")
            count += 1
    return count


def _rows(session: Session, query: str, params: dict | None = None) -> list[dict]:
    result = session.execute(text(query), params or {})
    return [dict(row) for row in result.mappings()]


def _db_now(session: Session) -> datetime:
    value = session.execute(text("SELECT timezone('UTC', now())")).scalar_one()
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def _safe_configuration(session: Session) -> dict:
    """Configuration utile à la reproductibilité, sans aucun secret réseau."""
    return {
        "cameras": _rows(session, """
            SELECT id, cam_name, location, is_active, latitude, longitude, bearing,
                   source_type, hik_status, staffing_min_agents, staffing_max_agents,
                   staffing_tolerance_s, staffing_work_schedule_id
            FROM camera ORDER BY id
        """),
        "zones": _rows(session, """
            SELECT id, camera_id, name, kind, polygon, color, is_active, threshold,
                   min_presence_s, work_schedule_id, created_at, updated_at
            FROM zone ORDER BY id
        """),
        "count_lines": _rows(session, """
            SELECT id, camera_id, name, point_a, point_b, in_direction, is_active,
                   created_at, updated_at
            FROM count_line ORDER BY id
        """),
        "work_schedules": _rows(session, """
            SELECT id, name, description, timezone, segments, absence_tolerance_s,
                   is_active, created_at, updated_at
            FROM work_schedule ORDER BY id
        """),
        "rules": _rows(session, """
            SELECT id, name, trigger, zone_id, work_schedule_id, conditions,
                   schedule, kind, severity, cooldown_s, is_active,
                   notify_channels, trigger_count, last_triggered_at,
                   created_at, updated_at
            FROM rule ORDER BY id
        """),
    }


def _current_manifest() -> tuple[Path, dict]:
    if not CURRENT.exists():
        raise SystemExit("Aucune campagne active : lancez d'abord la commande start.")
    marker = json.loads(CURRENT.read_text(encoding="utf-8"))
    run_dir = ROOT / marker["run_id"]
    manifest_path = run_dir / "manifest.json"
    return manifest_path, json.loads(manifest_path.read_text(encoding="utf-8"))


def start(run_id: str) -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    run_dir = ROOT / run_id
    if run_dir.exists() and any(run_dir.iterdir()):
        raise SystemExit(f"Le dossier de campagne existe déjà : {run_dir}")
    run_dir.mkdir(parents=True, exist_ok=True)

    with Session(engine) as session:
        started_at = _db_now(session)
        baseline = {
            "last_event_id": session.execute(text("SELECT coalesce(max(id), 0) FROM event")).scalar_one(),
            "last_alert_id": session.execute(text("SELECT coalesce(max(id), 0) FROM alert")).scalar_one(),
            "last_camera_status_id": session.execute(
                text("SELECT coalesce(max(id), 0) FROM camera_status_event")
            ).scalar_one(),
        }
        configuration = _safe_configuration(session)

    manifest = {
        "run_id": run_id,
        "status": "running",
        "started_at_utc": started_at,
        "ended_at_utc": None,
        "git_commit": os.getenv("OBSERVATION_GIT_COMMIT"),
        "audit_interval_seconds": int(
            os.getenv("PRESENCE_AUDIT_INTERVAL_SECONDS", "120")
        ),
        "metrics_interval_seconds": int(os.getenv("MEASURE_SAMPLE_SECONDS", "30")),
        "baseline": baseline,
    }
    _write_json(run_dir / "manifest.json", manifest)
    _write_json(run_dir / "configuration_start.json", configuration)
    _write_json(CURRENT, {"run_id": run_id, "started_at_utc": started_at})
    print(json.dumps(manifest, ensure_ascii=False, default=_json_value))


def _period_rows(session: Session, manifest: dict) -> dict[str, list[dict]]:
    params = {
        "start": manifest["started_at_utc"],
        "end": manifest.get("ended_at_utc") or _db_now(session).isoformat(),
    }
    return {
        "events": _rows(session, """
            SELECT e.id, e.camera_id, c.cam_name AS camera_name,
                   c.location AS camera_location, e.event_type, e.confidence,
                   e.snapshot_url, e.meta, e.timestamp
            FROM event e JOIN camera c ON c.id = e.camera_id
            WHERE e.timestamp >= :start AND e.timestamp <= :end
            ORDER BY e.timestamp, e.id
        """, params),
        "alerts": _rows(session, """
            SELECT id, event_id, kind, label, reason, camera_id, snapshot_url,
                   status, acknowledged_at, notified_at, notified_channel,
                   created_at, severity
            FROM alert
            WHERE created_at >= :start AND created_at <= :end
            ORDER BY created_at, id
        """, params),
        "camera_status": _rows(session, """
            SELECT id, camera_id, status, prev_status, reconnection_attempts,
                   reason, timestamp
            FROM camera_status_event
            WHERE timestamp >= :start AND timestamp <= :end
            ORDER BY timestamp, id
        """, params),
    }


def status() -> None:
    _path, manifest = _current_manifest()
    with Session(engine) as session:
        rows = _period_rows(session, manifest)
    event_types: dict[str, int] = {}
    for row in rows["events"]:
        kind = row["event_type"]
        event_types[kind] = event_types.get(kind, 0) + 1
    payload = {
        "run_id": manifest["run_id"],
        "started_at_utc": manifest["started_at_utc"],
        "events": len(rows["events"]),
        "event_types": event_types,
        "alerts": len(rows["alerts"]),
        "camera_status_transitions": len(rows["camera_status"]),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def export() -> None:
    manifest_path, manifest = _current_manifest()
    with Session(engine) as session:
        ended_at = _db_now(session)
        manifest["ended_at_utc"] = ended_at.isoformat()
        rows = _period_rows(session, manifest)
        configuration_end = _safe_configuration(session)

    run_dir = manifest_path.parent
    counts = {
        name: _write_jsonl(run_dir / f"{name}.jsonl", values)
        for name, values in rows.items()
    }
    _write_json(run_dir / "configuration_end.json", configuration_end)

    snapshots_dir = run_dir / "snapshots"
    snapshots_dir.mkdir(exist_ok=True)
    wanted = {
        row.get("snapshot_url")
        for values in (rows["events"], rows["alerts"])
        for row in values
        if row.get("snapshot_url")
    }
    copied = 0
    missing = []
    for snapshot_url in sorted(wanted):
        name = Path(str(snapshot_url)).name
        source = Path("/app/snapshots") / name
        if source.is_file():
            shutil.copy2(source, snapshots_dir / name)
            copied += 1
        else:
            missing.append(str(snapshot_url))

    event_types: dict[str, int] = {}
    for row in rows["events"]:
        kind = row["event_type"]
        event_types[kind] = event_types.get(kind, 0) + 1
    manifest.update({
        "status": "exported",
        "counts": counts,
        "event_types": event_types,
        "snapshots_referenced": len(wanted),
        "snapshots_copied": copied,
        "snapshots_missing": missing,
    })
    _write_json(manifest_path, manifest)
    CURRENT.unlink(missing_ok=True)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("start", "status", "export"))
    parser.add_argument("--run-id", default=os.getenv("OBSERVATION_RUN_ID"))
    args = parser.parse_args()
    if args.action == "start":
        if not args.run_id:
            raise SystemExit("--run-id ou OBSERVATION_RUN_ID est obligatoire.")
        start(args.run_id)
    elif args.action == "status":
        status()
    else:
        export()


if __name__ == "__main__":
    main()

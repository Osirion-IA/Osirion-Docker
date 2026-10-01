"""Génère des planches de contrôle des POST_VACANT d'une campagne."""
from __future__ import annotations

import math
import sys
from pathlib import Path

import cv2
import numpy as np
from sqlmodel import Session, select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import engine
from app.models.events import Event
from app.models.zones import Zone


BASELINE_ID = 314176
OUT = Path("/app/observation_runs/eval_20260827T145943Z/analysis")
CELL_W, IMAGE_H, LABEL_H = 384, 216, 74
COLS, ROWS = 4, 4


def render(event: Event, polygon) -> np.ndarray:
    path = Path("/app") / str(event.snapshot_url)
    image = cv2.imread(str(path))
    if image is None:
        image = np.zeros((IMAGE_H, CELL_W, 3), dtype=np.uint8)
        cv2.putText(image, "IMAGE ILLISIBLE", (30, 100), cv2.FONT_HERSHEY_SIMPLEX, .8, (0, 0, 255), 2)
    else:
        image = cv2.resize(image, (CELL_W, IMAGE_H), interpolation=cv2.INTER_AREA)
    if polygon:
        points = np.array(
            [[int(float(x) * CELL_W), int(float(y) * IMAGE_H)] for x, y in polygon],
            dtype=np.int32,
        )
        cv2.polylines(image, [points], True, (0, 255, 255), 2)

    meta = event.meta or {}
    decision = meta.get("decision") or {}
    canvas = np.zeros((IMAGE_H + LABEL_H, CELL_W, 3), dtype=np.uint8)
    canvas[:IMAGE_H] = image
    lines = [
        f"#{event.id} cam {event.camera_id} - {meta.get('zone_name', '')}",
        event.timestamp.strftime("%Y-%m-%d %H:%M:%S UTC"),
        f"detections={decision.get('frame_person_detections')} conf={decision.get('frame_max_confidence')}",
    ]
    for index, line in enumerate(lines):
        cv2.putText(
            canvas, line[:58], (7, IMAGE_H + 19 + index * 18),
            cv2.FONT_HERSHEY_SIMPLEX, .43, (235, 235, 235), 1, cv2.LINE_AA,
        )
    return canvas


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with Session(engine) as session:
        events = session.exec(
            select(Event).where(
                Event.id > BASELINE_ID,
                Event.event_type == "POST_VACANT",
            ).order_by(Event.timestamp)
        ).all()
        polygons = {
            zone.id: zone.polygon
            for zone in session.exec(select(Zone)).all()
        }

    cells = [render(event, polygons.get((event.meta or {}).get("zone_id"))) for event in events]
    page_size = COLS * ROWS
    for page_no in range(math.ceil(len(cells) / page_size)):
        page_cells = cells[page_no * page_size:(page_no + 1) * page_size]
        blank = np.zeros_like(cells[0])
        page_cells += [blank] * (page_size - len(page_cells))
        rows = [
            np.hstack(page_cells[row * COLS:(row + 1) * COLS])
            for row in range(ROWS)
        ]
        sheet = np.vstack(rows)
        cv2.imwrite(str(OUT / f"vacancies_{page_no + 1:02d}.jpg"), sheet, [cv2.IMWRITE_JPEG_QUALITY, 90])
    print(f"events={len(events)} sheets={math.ceil(len(cells)/page_size)} output={OUT}")


if __name__ == "__main__":
    main()

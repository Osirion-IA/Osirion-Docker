"""Audit visuel enrichi des POST_VACANT : boites + confiance + ancrage + polygone."""
import json, math
from pathlib import Path
import cv2, numpy as np
from ultralytics import YOLO

MANIFEST = Path("/work/vacancies.json")
SNAP = Path("/snap")
OUT = Path("/work/out"); OUT.mkdir(parents=True, exist_ok=True)
CONF_FLOOR = 0.10      # plancher tracker (BYTE) : revele les detections faibles
ACCEPT = 0.30          # PERSON_DETECTION_CONFIDENCE reel (.env)
CELL_W, CELL_H, LABEL_H = 640, 360, 92

def inside(poly_px, pt):
    return cv2.pointPolygonTest(poly_px, (float(pt[0]), float(pt[1])), False) >= 0

def overlap_ratio(poly_px, box, shape):
    m1 = np.zeros(shape[:2], np.uint8); cv2.fillPoly(m1, [poly_px], 1)
    m2 = np.zeros(shape[:2], np.uint8)
    x1, y1, x2, y2 = [int(v) for v in box]
    cv2.rectangle(m2, (x1, y1), (x2, y2), 1, -1)
    a = int((m2 > 0).sum())
    return 0.0 if a == 0 else float((m1 & m2).sum()) / a

def main():
    items = json.loads(MANIFEST.read_text())
    model = YOLO("/app/yolo26s.pt")
    verdicts = []
    cells = {}
    for it in items:
        p = SNAP / Path(it["snapshot"]).name
        img = cv2.imread(str(p))
        if img is None:
            verdicts.append({**{k: it[k] for k in ("id", "camera_id", "zone_id")},
                             "verdict": "IMAGE_ILLISIBLE", "n_in": 0, "n_box": 0, "best_in": 0.0})
            continue
        H, W = img.shape[:2]
        poly_px = np.array([[int(x * W), int(y * H)] for x, y in it["polygon"]], np.int32)

        r = model.predict(img, imgsz=960, conf=CONF_FLOOR, classes=[0], verbose=False)[0]
        boxes = [(float(b[0]), float(b[1]), float(b[2]), float(b[3]), float(c))
                 for b, c in zip(r.boxes.xyxy.tolist(), r.boxes.conf.tolist())]

        vis = img.copy()
        cv2.polylines(vis, [poly_px], True, (0, 255, 255), 3)
        n_in = 0; best_in = 0.0
        for x1, y1, x2, y2, c in boxes:
            foot = ((x1 + x2) / 2.0, y2)
            ov = overlap_ratio(poly_px, (x1, y1, x2, y2), img.shape)
            member = inside(poly_px, foot) or ov >= 0.5
            if member:
                n_in += 1; best_in = max(best_in, c)
            col = (0, 0, 255) if member else ((0, 200, 0) if c >= ACCEPT else (0, 165, 255))
            cv2.rectangle(vis, (int(x1), int(y1)), (int(x2), int(y2)), col, 2)
            cv2.circle(vis, (int(foot[0]), int(foot[1])), 6, col, -1)
            cv2.putText(vis, f"{c:.2f}{' DANS' if member else ''}", (int(x1), max(14, int(y1) - 6)),
                        cv2.FONT_HERSHEY_SIMPLEX, .55, col, 2, cv2.LINE_AA)

        if n_in and best_in >= ACCEPT:   v = "FAUX POSITIF PROBABLE"
        elif n_in:                       v = "DOUTEUX (personne faible dans zone)"
        elif boxes:                      v = "VRAI VACANT (personnes hors zone)"
        else:                            v = "VRAI VACANT (aucune personne)"
        verdicts.append({"id": it["id"], "camera_id": it["camera_id"], "zone_id": it["zone_id"],
                         "ts": it["ts"], "verdict": v, "n_in": n_in, "n_box": len(boxes),
                         "best_in": round(best_in, 4),
                         "db_det": it["det"], "db_conf": it["conf"]})

        cell = np.zeros((CELL_H + LABEL_H, CELL_W, 3), np.uint8)
        cell[:CELL_H] = cv2.resize(vis, (CELL_W, CELL_H), interpolation=cv2.INTER_AREA)
        lines = [f"#{it['id']} cam{it['camera_id']} {it['zone_name'][:30]}",
                 f"{it['ts'][:16].replace('T',' ')} UTC  (local +1h)",
                 f"boites={len(boxes)} dans_zone={n_in} meilleure_dans={best_in:.2f}",
                 v]
        for i, ln in enumerate(lines):
            colr = (0, 165, 255) if (i == 3 and n_in) else (235, 235, 235)
            cv2.putText(cell, ln[:64], (8, CELL_H + 20 + i * 20),
                        cv2.FONT_HERSHEY_SIMPLEX, .5, colr, 1, cv2.LINE_AA)
        cells.setdefault(it["camera_id"], []).append(cell)

    COLS = 3
    for cam, cl in sorted(cells.items()):
        rows = []
        for i in range(0, len(cl), COLS):
            row = cl[i:i + COLS]
            row += [np.zeros_like(cl[0])] * (COLS - len(row))
            rows.append(np.hstack(row))
        cv2.imwrite(str(OUT / f"audit_cam{cam:03d}.jpg"), np.vstack(rows),
                    [cv2.IMWRITE_JPEG_QUALITY, 88])
    (Path("/work") / "verdicts.json").write_text(json.dumps(verdicts, indent=1))
    print(f"images={len(items)} cameras={len(cells)} -> {OUT}")

main()

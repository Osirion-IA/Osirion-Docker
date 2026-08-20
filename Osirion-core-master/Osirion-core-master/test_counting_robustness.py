"""
Test de robustesse du COMPTAGE - Osirion Core

Vérifie les invariants qui protègent les compteurs (sortie « produit » du système)
contre les ratés de détection isolés. Chacun correspond à un sous-comptage constaté :

  1. Tracker : une frame ratée ne doit pas retirer la personne du Scene Model
     (auparavant ~3 frames d'absence, le tracker réexigeant min_hits appariements).
  2. Tracker : une personne SORTIE DU CHAMP ne doit pas rester maintenue (sur-comptage).
  3. Ligne : un franchissement doit être compté même si la personne est ratée une
     frame au passage (auparavant l'état par track était purgé → passage perdu).
  4. Ligne : une position MAINTENUE (non observée) ne doit jamais compter.
  5. Occupation : un raté isolé ne doit pas écrire une valeur fausse en base.
  6. Attente : une occlusion brève ne doit pas couper un temps de présence en deux.
  7. Zone d'exclusion : le décor trompeur est filtré avant le tracking.

Exécution — dans le conteneur core (seul endroit où torch/filterpy sont installés ;
la racine du projet n'est pas bind-montée, d'où la copie préalable) :
    docker cp test_counting_robustness.py osirion-core:/app/ \
      && docker exec -w /app osirion-core python test_counting_robustness.py
"""
import os
import sys
import time
import types

sys.path.append(os.getcwd())

import numpy as np

from core import event_dispatch
from core.event_engine import EventEngine
from core.trackers.oc_sort import OCSortTrackerAdapter

W, H = 1280, 720
FAILS = []


def check(label, cond, detail=""):
    print(f"{'✅' if cond else '❌'} {label}{(' — ' + detail) if detail else ''}")
    if not cond:
        FAILS.append(label)


def make_tracker(max_coast):
    return OCSortTrackerAdapter(types.SimpleNamespace(
        det_thresh=0.3, max_age=30, min_hits=3, iou_threshold=0.3,
        delta_t=3, inertia=0.2, use_byte=True, low_thresh=0.1, max_coast=max_coast,
    ))


def make_engine(zones=None, lines=None, ignore=None):
    cfg = types.SimpleNamespace(
        ZONES_REFRESH_SECONDS=30, CROWD_MIN_SECONDS=3.0, OCCUPANCY_EMIT_INTERVAL=0.0,
        DWELL_MIN_SECONDS=0.1, OCCUPANCY_SMOOTH_SECONDS=1.5,
        DWELL_EXIT_GRACE_SECONDS=0.3, TRACK_STATE_TTL_FRAMES=90,
        LINE_CROSS_MARGIN=0.02, LINE_CROSS_COOLDOWN_FRAMES=15,
        LINE_CROSS_MIN_AGE_FRAMES=3,
    )
    eng = EventEngine(1, cfg)          # sans start() : aucun accès réseau
    eng.zones, eng.lines, eng._ignore_polygons = zones or [], lines or [], ignore or []
    return eng


def capture():
    """Remplace l'émission réseau des événements par une collecte en mémoire."""
    events = []
    event_dispatch.dispatch = (
        lambda cam, typ, meta=None, frame=None, confidence=None: events.append((typ, meta))
    )
    return events


def box(x, w=50):
    return np.array([[x, 100, min(x + w, W), 300, 0.9]], dtype=float)


# ── 1-2. Tracker : sursis d'occlusion, mais pas au bord de l'image ────────────
def test_occlusion_ne_fait_pas_disparaitre():
    tr = make_tracker(8)
    published = []
    for i in range(14):
        dets = np.empty((0, 5)) if i == 9 else box(500.0 + i * 8)
        published.append([(t.track_id, t.predicted) for t in tr.update(dets, [H, W], [H, W])])
    absences = sum(1 for p in published[9:] if not p)
    ids = {tid for p in published for tid, _ in p}
    check("occlusion d'une frame : la personne reste comptée", absences == 0,
          f"{absences} frame(s) d'absence")
    check("occlusion d'une frame : l'identifiant est conservé", len(ids) == 1, f"ids={ids}")
    check("occlusion d'une frame : la position maintenue est signalée",
          any(pred for _, pred in published[9]))


def test_sortie_du_champ_non_maintenue():
    tr = make_tracker(8)
    for i in range(10):                       # marche continue vers le bord droit
        tr.update(box(1100.0 + i * 15), [H, W], [H, W])
    check("sortie du champ : la personne n'est pas maintenue (pas de sur-comptage)",
          len(tr.update(np.empty((0, 5)), [H, W], [H, W])) == 0)

    tr2 = make_tracker(8)                     # contrôle : occlusion au centre
    for i in range(6):
        tr2.update(box(600.0 + i * 5), [H, W], [H, W])
    check("occlusion au centre : la personne reste comptée",
          len(tr2.update(np.empty((0, 5)), [H, W], [H, W])) == 1)


# ── 3-4. Comptage de ligne ────────────────────────────────────────────────────
LINE = {"id": 1, "name": "Entrée", "point_a": [0.5, 0.0], "point_b": [0.5, 1.0],
        "in_direction": "positive", "is_active": True}


def test_franchissement_malgre_frame_ratee():
    eng, events = make_engine(lines=[LINE]), capture()
    for x in (0.30, 0.34, 0.38, 0.42, 0.46, None, 0.54, 0.58, 0.62, 0.66):
        eng.process([] if x is None else [{"track_id": 7, "x": x, "y": 0.5, "predicted": False}])
    n = sum(1 for t, _ in events if t == "LINE_CROSSED")
    check("ligne : franchissement compté malgré une frame ratée au passage", n == 1,
          f"{n} événement(s)")


def test_position_maintenue_ne_compte_pas():
    eng, events = make_engine(lines=[LINE]), capture()
    for x in (0.30, 0.34, 0.38, 0.42):
        eng.process([{"track_id": 7, "x": x, "y": 0.5, "predicted": False}])
    for _ in range(5):
        eng.process([{"track_id": 7, "x": 0.70, "y": 0.5, "predicted": True}])
    check("ligne : une position maintenue ne déclenche aucun comptage",
          not [e for e in events if e[0] == "LINE_CROSSED"])


# ── 5-6. Occupation et temps d'attente ────────────────────────────────────────
FULL_FRAME = [[0, 0], [1, 0], [1, 1], [0, 1]]


def test_occupation_lissee():
    zone = {"id": 3, "name": "Hall", "kind": "occupancy", "is_active": True,
            "polygon": FULL_FRAME}
    eng, events = make_engine(zones=[zone]), capture()
    deux = [{"track_id": i, "x": 0.5, "y": 0.5, "predicted": False} for i in (1, 2)]
    for tracks in (deux, deux, deux, [], deux, deux, deux):     # 1 frame ratée
        eng.process(tracks)
    counts = [m["count"] for t, m in events if t == "ZONE_OCCUPANCY_CHANGED"]
    check("occupation : un raté isolé n'écrit pas de 0 en base", 0 not in counts,
          f"valeurs publiées={counts}")


def test_attente_non_coupee_par_occlusion():
    zone = {"id": 4, "name": "File", "kind": "queue", "is_active": True,
            "polygon": FULL_FRAME}
    eng, events = make_engine(zones=[zone]), capture()
    dedans = [{"track_id": 9, "x": 0.5, "y": 0.5, "predicted": False}]
    eng.process(dedans)
    time.sleep(0.4)
    eng.process([])            # occlusion → sortie probable
    time.sleep(0.1)
    eng.process(dedans)        # retour dans le délai de grâce → la présence continue
    time.sleep(0.4)
    eng.process([])            # vraie sortie
    time.sleep(0.4)
    eng.process([])            # au-delà de la grâce → présence confirmée
    dwells = [m["dwell_s"] for t, m in events if t == "ZONE_DWELL"]
    check("attente : une occlusion ne coupe pas le temps de présence en deux",
          len(dwells) == 1 and dwells[0] >= 0.8, f"dwells={dwells}")


# ── 7. Zone d'exclusion ───────────────────────────────────────────────────────
def test_zone_exclusion():
    eng = make_engine(ignore=[[[0.0, 0.0], [0.5, 0.0], [0.5, 1.0], [0.0, 1.0]]])
    kept = eng.filter_ignored([[100, 100, 200, 400, 0.9],      # dans la zone ignorée
                               [900, 100, 1000, 400, 0.9]],    # hors zone
                              W, H)
    check("zone d'exclusion : la détection du décor est jetée avant le tracking",
          len(kept) == 1 and kept[0][0] == 900, f"{len(kept)} boîte(s) conservée(s)")


if __name__ == "__main__":
    print("=" * 60)
    print("🎯 ROBUSTESSE DU COMPTAGE - OSIRION-CORE")
    print("=" * 60)
    for fn in (test_occlusion_ne_fait_pas_disparaitre, test_sortie_du_champ_non_maintenue,
               test_franchissement_malgre_frame_ratee, test_position_maintenue_ne_compte_pas,
               test_occupation_lissee, test_attente_non_coupee_par_occlusion,
               test_zone_exclusion):
        fn()
    print("=" * 60)
    print("✅ Tous les invariants tiennent." if not FAILS else f"❌ Échecs : {FAILS}")
    sys.exit(1 if FAILS else 0)

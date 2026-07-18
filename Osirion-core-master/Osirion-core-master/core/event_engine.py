# core/event_engine.py
"""
Event Engine — transforme le Scene Model anonyme (tracks : point au sol + vitesse)
en ÉVÉNEMENTS métier, pour UNE caméra. CPU pur, sur le thread caméra, mais très
léger (point-dans-polygone / franchissement pour quelques tracks × quelques zones).

Événements produits (émis en fire-and-forget via core.event_dispatch) :
  - ZONE_OCCUPANCY_CHANGED : l'occupation d'une zone change (throttlé).
  - CROWD_DETECTED         : occupation ≥ seuil de la zone, soutenue T secondes.
  - LINE_CROSSED           : un track franchit une ligne de comptage (sens in/out).

Les zones/lignes sont rafraîchies dans un THREAD DÉDIÉ (jamais de réseau sur le
thread caméra). process() ne lit que des listes en cache (swap de référence atomique).
"""
import threading
import time
from typing import Dict, List

from core.geometry import point_in_polygon, segment_side
from core import event_dispatch
from services.zones_fetching_service import fetch_zones, fetch_lines
from utils.logger import get_logger

logger = get_logger(__name__)


class EventEngine:
    def __init__(self, camera_id: int, config):
        self.camera_id = camera_id
        self.config = config
        self.zones: List[Dict] = []
        self.lines: List[Dict] = []

        self._refresh_interval = max(5, int(getattr(config, "ZONES_REFRESH_SECONDS", 30)))
        self._crowd_min_s = float(getattr(config, "CROWD_MIN_SECONDS", 3.0))
        self._occ_interval = float(getattr(config, "OCCUPANCY_EMIT_INTERVAL", 2.0))
        self._dwell_min_s = float(getattr(config, "DWELL_MIN_SECONDS", 1.0))

        # État (muté UNIQUEMENT par le thread caméra dans process()).
        self._occ_last: Dict[int, int] = {}
        self._occ_last_emit: Dict[int, float] = {}
        self._crowd_since: Dict[int, float] = {}
        self._crowd_active: Dict[int, bool] = {}
        self._line_side: Dict[int, Dict[int, float]] = {}
        # Appartenance + horodatage d'entrée par zone → temps de présence (ZONE_DWELL).
        self._zone_members: Dict[int, set] = {}
        self._zone_entry: Dict[int, Dict[int, float]] = {}

        # Rafraîchisseur zones/lignes (thread dédié → pas de réseau côté caméra).
        self._stop = threading.Event()
        self._refresher: threading.Thread = None

    # ── Cycle de vie ────────────────────────────────────────────────────────
    def start(self) -> None:
        # 1er chargement synchrone (une fois, au démarrage de la caméra) puis
        # rafraîchissement périodique en tâche de fond.
        self._reload()
        self._refresher = threading.Thread(
            target=self._refresh_loop, name=f"zones-refresh-{self.camera_id}", daemon=True
        )
        self._refresher.start()

    def stop(self) -> None:
        self._stop.set()
        if self._refresher is not None and self._refresher.is_alive():
            self._refresher.join(timeout=2)

    def _reload(self) -> None:
        try:
            # Swap de référence atomique (le thread caméra lit l'ancienne ou la
            # nouvelle liste, jamais un état partiel).
            self.zones = fetch_zones(self.camera_id) or []
            self.lines = fetch_lines(self.camera_id) or []
        except Exception as e:
            logger.debug(f"[event-engine cam={self.camera_id}] reload KO : {e}")

    def _refresh_loop(self) -> None:
        while not self._stop.wait(self._refresh_interval):
            self._reload()

    # ── Traitement d'une frame (thread caméra) ──────────────────────────────
    def process(self, tracks_norm: List[Dict], frame=None) -> None:
        """tracks_norm : [{'track_id': int, 'x': float, 'y': float}] avec (x, y) =
        point au sol NORMALISÉ dans [0,1]. Émet les événements (fire-and-forget)."""
        now = time.time()
        zones = self.zones          # référence locale (swap atomique)
        lines = self.lines

        # ── Occupation + attroupement ──
        for z in zones:
            if not z.get("is_active", True):
                continue
            zid = z.get("id")
            poly = z.get("polygon") or []
            if not poly:
                continue
            members = {t["track_id"] for t in tracks_norm if point_in_polygon(t["x"], t["y"], poly)}
            count = len(members)

            # ── Temps de présence (ZONE_DWELL) : entrées/sorties de la zone ──
            old_members = self._zone_members.get(zid, set())
            entry = self._zone_entry.setdefault(zid, {})
            for tid in (members - old_members):
                entry[tid] = now
            for tid in (old_members - members):
                t0 = entry.pop(tid, None)
                if t0 is not None:
                    dwell = round(now - t0, 1)
                    if dwell >= self._dwell_min_s:
                        event_dispatch.dispatch(
                            self.camera_id, "ZONE_DWELL",
                            meta={"zone_id": zid, "zone_name": z.get("name"),
                                  "kind": z.get("kind"), "dwell_s": dwell},
                        )
            self._zone_members[zid] = members

            if self._occ_last.get(zid) != count and (now - self._occ_last_emit.get(zid, 0.0)) >= self._occ_interval:
                self._occ_last[zid] = count
                self._occ_last_emit[zid] = now
                event_dispatch.dispatch(
                    self.camera_id, "ZONE_OCCUPANCY_CHANGED",
                    meta={"zone_id": zid, "zone_name": z.get("name"),
                          "kind": z.get("kind"), "count": count},
                )

            thr = z.get("threshold")
            if thr:
                if count >= thr:
                    since = self._crowd_since.get(zid)
                    if since is None:
                        self._crowd_since[zid] = now
                    elif (now - since) >= self._crowd_min_s and not self._crowd_active.get(zid):
                        self._crowd_active[zid] = True
                        event_dispatch.dispatch(
                            self.camera_id, "CROWD_DETECTED",
                            meta={"zone_id": zid, "zone_name": z.get("name"),
                                  "count": count, "threshold": thr},
                            frame=frame, confidence=1.0,
                        )
                else:
                    self._crowd_since.pop(zid, None)
                    self._crowd_active.pop(zid, None)

        # ── Franchissement de ligne (comptage) ──
        cur_ids = {t["track_id"] for t in tracks_norm}
        for ln in lines:
            if not ln.get("is_active", True):
                continue
            lid = ln.get("id")
            a = ln.get("point_a") or []
            b = ln.get("point_b") or []
            if len(a) != 2 or len(b) != 2:
                continue
            sides = self._line_side.setdefault(lid, {})
            in_positive = (ln.get("in_direction", "positive") == "positive")
            for t in tracks_norm:
                s = segment_side(a[0], a[1], b[0], b[1], t["x"], t["y"])
                prev_s = sides.get(t["track_id"])
                sides[t["track_id"]] = s
                if prev_s is not None and prev_s != 0 and s != 0 and (prev_s > 0) != (s > 0):
                    direction = "in" if ((s > 0) == in_positive) else "out"
                    event_dispatch.dispatch(
                        self.camera_id, "LINE_CROSSED",
                        meta={"line_id": lid, "line_name": ln.get("name"), "direction": direction},
                    )
            # Purge des tracks disparus (borne mémoire).
            for tid in [k for k in sides if k not in cur_ids]:
                sides.pop(tid, None)

    def zones_for_point(self, x: float, y: float) -> List[int]:
        """Ids des zones contenant le point (normalisé) — enrichit le Scene Model."""
        out = []
        for z in self.zones:
            poly = z.get("polygon") or []
            if poly and point_in_polygon(x, y, poly):
                out.append(z.get("id"))
        return out

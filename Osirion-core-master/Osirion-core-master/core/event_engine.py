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
import math
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
        # Robustesse du comptage de ligne (anti-jitter / anti-ID-switch) :
        self._line_margin = float(getattr(config, "LINE_CROSS_MARGIN", 0.02))         # bande morte perpendiculaire (unités image [0,1])
        self._line_cooldown = int(getattr(config, "LINE_CROSS_COOLDOWN_FRAMES", 15))  # frames min entre 2 comptages d'un même track
        self._line_min_age = int(getattr(config, "LINE_CROSS_MIN_AGE_FRAMES", 3))     # âge de track min avant de compter

        # État (muté UNIQUEMENT par le thread caméra dans process()).
        self._occ_last: Dict[int, int] = {}
        self._occ_last_emit: Dict[int, float] = {}
        self._crowd_since: Dict[int, float] = {}
        self._crowd_active: Dict[int, bool] = {}
        # Côté ENGAGÉ par (ligne, track) : ne bascule qu'au-delà de la bande morte
        # (hystérésis → un track à cheval sur la ligne ne compte pas N fois).
        self._line_committed: Dict[int, Dict[int, int]] = {}
        self._line_last_cross: Dict[int, Dict[int, int]] = {}   # dernier frame compté par (ligne, track)
        self._track_age: Dict[int, int] = {}                    # nb de frames vues par track (âge)
        self._frame_no: int = 0
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

        # Âge des tracks (compteur d'observations) + numéro de frame → garde-fous du
        # comptage de ligne. Purge des tracks disparus (borne mémoire).
        self._frame_no += 1
        live_ids = {t["track_id"] for t in tracks_norm}
        for tid in live_ids:
            self._track_age[tid] = self._track_age.get(tid, 0) + 1
        for tid in [k for k in self._track_age if k not in live_ids]:
            del self._track_age[tid]

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

            prev_count = self._occ_last.get(zid)
            entered = (prev_count in (None, 0)) and count > 0   # transition 0 → occupé
            changed = prev_count != count
            due = (now - self._occ_last_emit.get(zid, 0.0)) >= self._occ_interval
            if changed and (entered or due):
                self._occ_last[zid] = count
                self._occ_last_emit[zid] = now
                event_dispatch.dispatch(
                    self.camera_id, "ZONE_OCCUPANCY_CHANGED",
                    meta={"zone_id": zid, "zone_name": z.get("name"),
                          "kind": z.get("kind"), "count": count},
                    # Snapshot uniquement à l'ENTRÉE (0→occupé) → l'intrusion a une
                    # photo, sans coût d'encodage sur les frames normales.
                    frame=(frame if entered else None),
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

        # ── Franchissement de ligne (comptage) — robuste au jitter et aux ID-switch ──
        # Hystérésis : le côté « engagé » d'un track ne change qu'au-delà d'une BANDE
        # MORTE (marge perpendiculaire) → un track à cheval sur la ligne ne génère
        # plus N passages. Un comptage exige en plus un ÂGE de track minimal (évite
        # les artefacts de (ré)apparition après un changement d'identifiant) et un
        # COOLDOWN par (track, ligne) (évite les rebonds trop rapprochés).
        cur_ids = live_ids
        for ln in lines:
            if not ln.get("is_active", True):
                continue
            lid = ln.get("id")
            a = ln.get("point_a") or []
            b = ln.get("point_b") or []
            if len(a) != 2 or len(b) != 2:
                continue
            ax, ay, bx, by = a[0], a[1], b[0], b[1]
            seg_len = math.hypot(bx - ax, by - ay)
            if seg_len < 1e-6:            # ligne dégénérée (2 points confondus)
                continue
            committed = self._line_committed.setdefault(lid, {})
            last_cross = self._line_last_cross.setdefault(lid, {})
            in_positive = (ln.get("in_direction", "positive") == "positive")
            for t in tracks_norm:
                tid = t["track_id"]
                # Distance perpendiculaire SIGNÉE, en unités image normalisées.
                dist = segment_side(ax, ay, bx, by, t["x"], t["y"]) / seg_len
                if dist > self._line_margin:
                    side = 1
                elif dist < -self._line_margin:
                    side = -1
                else:
                    continue             # bande morte → côté engagé inchangé (anti-jitter)
                prev = committed.get(tid)
                committed[tid] = side
                if prev is None or prev == side:
                    continue             # 1re observation claire, ou pas de bascule
                if self._track_age.get(tid, 0) < self._line_min_age:
                    continue             # track trop jeune → probable (ré)apparition
                if self._frame_no - last_cross.get(tid, -10 ** 9) < self._line_cooldown:
                    continue             # cooldown : rebond trop rapproché
                last_cross[tid] = self._frame_no
                direction = "in" if ((side > 0) == in_positive) else "out"
                event_dispatch.dispatch(
                    self.camera_id, "LINE_CROSSED",
                    meta={"line_id": lid, "line_name": ln.get("name"), "direction": direction},
                )
            # Purge des tracks disparus (borne mémoire).
            for tid in [k for k in committed if k not in cur_ids]:
                committed.pop(tid, None)
                last_cross.pop(tid, None)

    def zones_for_point(self, x: float, y: float) -> List[int]:
        """Ids des zones contenant le point (normalisé) — enrichit le Scene Model."""
        out = []
        for z in self.zones:
            poly = z.get("polygon") or []
            if poly and point_in_polygon(x, y, poly):
                out.append(z.get("id"))
        return out

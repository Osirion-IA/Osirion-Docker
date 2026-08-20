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

Robustesse du comptage (les compteurs sont la sortie « produit » du système) :
  - l'état par track (côté engagé d'une ligne, âge) survit à une disparition brève
    via un TTL — sans quoi une personne ratée UNE frame au passage d'une ligne
    repartait de zéro et son franchissement n'était JAMAIS compté ;
  - l'occupation publiée est lissée temporellement (médiane glissante) : un raté de
    détection isolé n'écrit plus une valeur fausse dans l'historique analytique ;
  - une sortie de zone n'est confirmée qu'après un délai de grâce, pour qu'une
    occlusion brève ne coupe pas un temps de présence en deux (sous-estimation de
    l'attente) ;
  - les zones d'exclusion (kind « ignore ») retirent les détections récurrentes sur
    un décor trompeur (affiche, écran, reflet) AVANT le tracking.
"""
import math
import threading
import time
from collections import deque
from typing import Dict, List

from core.geometry import point_in_polygon, segment_side
from core import event_dispatch
from services.zones_fetching_service import fetch_zones, fetch_lines
from utils.logger import get_logger

logger = get_logger(__name__)

# Type de zone « exclusion » : ne produit AUCUN événement ; toute détection dont le
# point au sol y tombe est jetée avant le tracking (décor trompeur).
ZONE_IGNORE = "ignore"


class EventEngine:
    def __init__(self, camera_id: int, config):
        self.camera_id = camera_id
        self.config = config
        self.zones: List[Dict] = []        # zones ANALYTIQUES (hors exclusion)
        self.lines: List[Dict] = []
        self._ignore_polygons: List[List] = []   # polygones des zones d'exclusion actives

        self._refresh_interval = max(5, int(getattr(config, "ZONES_REFRESH_SECONDS", 30)))
        self._crowd_min_s = float(getattr(config, "CROWD_MIN_SECONDS", 3.0))
        self._occ_interval = float(getattr(config, "OCCUPANCY_EMIT_INTERVAL", 2.0))
        self._dwell_min_s = float(getattr(config, "DWELL_MIN_SECONDS", 1.0))
        # Fenêtre de lissage (s) de l'occupation : la valeur publiée est la médiane
        # des comptages de la fenêtre → un raté de détection isolé n'écrit plus un
        # point faux dans l'historique. 0 = pas de lissage (valeur instantanée).
        self._occ_smooth_s = float(getattr(config, "OCCUPANCY_SMOOTH_SECONDS", 1.5))
        # Délai (s) avant de confirmer une sortie de zone : une réapparition dans ce
        # délai POURSUIT la présence en cours au lieu d'ouvrir un 2ᵉ dwell (sans quoi
        # toute occlusion coupe l'attente mesurée en deux).
        self._dwell_grace_s = float(getattr(config, "DWELL_EXIT_GRACE_SECONDS", 2.0))
        # Délai (s) de CONFIRMATION de présence, par DÉFAUT : une personne n'est
        # comptée dans une zone qu'après y être restée sans interruption pendant ce
        # délai. Chaque zone peut le surcharger via son champ `min_presence_s`
        # (0 = immédiat, pour l'intrusion). Voir _min_presence().
        self._zone_min_presence = max(
            0.0, float(getattr(config, "ZONE_MIN_PRESENCE_SECONDS", 5.0))
        )
        # Durée de survie (frames) de l'état par track après sa dernière apparition.
        self._state_ttl = int(getattr(config, "TRACK_STATE_TTL_FRAMES", 90))
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
        self._track_age: Dict[int, int] = {}                    # nb d'observations réelles par track
        self._track_last_seen: Dict[int, int] = {}              # dernier frame où le track était publié
        self._frame_no: int = 0
        # Appartenance + horodatage d'entrée par zone → temps de présence (ZONE_DWELL).
        self._zone_members: Dict[int, set] = {}
        self._zone_entry: Dict[int, Dict[int, float]] = {}
        # Sorties de zone EN ATTENTE de confirmation (tid → instant de sortie).
        self._zone_pending_exit: Dict[int, Dict[int, float]] = {}
        # Fenêtre glissante des comptages bruts par zone → occupation lissée.
        self._occ_window: Dict[int, deque] = {}

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
            zones = fetch_zones(self.camera_id) or []
            # Les zones d'EXCLUSION sont retirées des zones analytiques : elles ne
            # produisent aucun événement, elles filtrent en amont (filter_ignored).
            self._ignore_polygons = [
                z.get("polygon") for z in zones
                if z.get("kind") == ZONE_IGNORE and z.get("is_active", True)
                and (z.get("polygon") or [])
            ]
            self.zones = [z for z in zones if z.get("kind") != ZONE_IGNORE]
            self.lines = fetch_lines(self.camera_id) or []
        except Exception as e:
            logger.debug(f"[event-engine cam={self.camera_id}] reload KO : {e}")

    # ── Filtrage amont (appelé par le thread caméra, avant le tracking) ─────
    def filter_ignored(self, boxes: List, frame_w: int, frame_h: int) -> List:
        """Retire les détections dont le point au sol tombe dans une zone d'exclusion.

        `boxes` : [[x1, y1, x2, y2, score], …] en pixels frame. Appelé AVANT le
        tracker → un décor trompeur (affiche, écran, reflet) ne crée jamais de track,
        donc n'entre ni dans l'occupation ni dans les comptages.
        """
        polys = self._ignore_polygons           # référence locale (swap atomique)
        if not polys or not boxes or not frame_w or not frame_h:
            return boxes
        kept = []
        for b in boxes:
            fx = ((b[0] + b[2]) / 2.0) / frame_w
            fy = b[3] / frame_h
            if any(point_in_polygon(fx, fy, p) for p in polys):
                continue
            kept.append(b)
        return kept

    def _refresh_loop(self) -> None:
        while not self._stop.wait(self._refresh_interval):
            self._reload()

    # ── Traitement d'une frame (thread caméra) ──────────────────────────────
    def process(self, tracks_norm: List[Dict], frame=None) -> None:
        """tracks_norm : [{'track_id': int, 'x': float, 'y': float, 'predicted': bool}]
        avec (x, y) = point au sol NORMALISÉ dans [0,1] et `predicted` = position
        MAINTENUE (track en sursis, non observé sur cette frame). Émet les événements
        (fire-and-forget)."""
        now = time.time()
        zones = self.zones          # référence locale (swap atomique)
        lines = self.lines

        # Âge des tracks (nb d'OBSERVATIONS réelles) + numéro de frame → garde-fous
        # du comptage de ligne.
        self._frame_no += 1
        for t in tracks_norm:
            tid = t["track_id"]
            self._track_last_seen[tid] = self._frame_no
            if not t.get("predicted"):
                self._track_age[tid] = self._track_age.get(tid, 0) + 1

        # L'état par track n'est PLUS purgé dès qu'il manque une frame : il survit
        # TRACK_STATE_TTL_FRAMES. Purger sur absence faisait repartir le côté engagé
        # à « inconnu », donc perdait le franchissement de toute personne ratée une
        # seule frame près d'une ligne (sous-comptage silencieux des entrées).
        if self._frame_no % 30 == 0:
            self._purge_stale_tracks()

        # ── Occupation + attroupement ──
        for z in zones:
            if not z.get("is_active", True):
                continue
            zid = z.get("id")
            poly = z.get("polygon") or []
            if not poly:
                continue
            # Appartenance GÉOMÉTRIQUE (brute) : elle pilote la machine à états
            # entrée/sortie, mais ne suffit PLUS à être compté (cf. confirmés).
            members = {t["track_id"] for t in tracks_norm if point_in_polygon(t["x"], t["y"], poly)}

            # ── Temps de présence (ZONE_DWELL) : entrées/sorties de la zone ──
            # Une sortie n'est confirmée qu'après un DÉLAI DE GRÂCE : si le track
            # revient avant, la présence en cours se poursuit (pas de dwell coupé
            # en deux, donc pas d'attente sous-estimée) — et comme son horodatage
            # d'entrée est conservé, une occlusion ne lui réimpose pas le délai de
            # confirmation ci-dessous.
            old_members = self._zone_members.get(zid, set())
            entry = self._zone_entry.setdefault(zid, {})
            pending = self._zone_pending_exit.setdefault(zid, {})
            for tid in (members - old_members):
                if pending.pop(tid, None) is None:
                    entry[tid] = now          # vraie entrée (pas un retour de grâce)
            for tid in (old_members - members):
                pending.setdefault(tid, now)  # sortie probable → à confirmer
            self._zone_members[zid] = members

            min_presence = self._min_presence(z)

            # ── Sorties CONFIRMÉES (délai de grâce écoulé) → temps de présence ──
            # Purgées AVANT le calcul de l'occupation ci-dessous : une présence
            # close ne doit plus peser sur le compte de la frame courante.
            for tid in [k for k, t_exit in pending.items()
                        if (now - t_exit) >= self._dwell_grace_s]:
                t_exit = pending.pop(tid)
                t0 = entry.pop(tid, None)
                if t0 is not None:
                    # Durée mesurée depuis l'entrée RÉELLE (géométrique) et jusqu'à
                    # la sortie, pas jusqu'à sa confirmation : le verrou filtre QUI
                    # compte, il ne rogne pas l'attente mesurée (sans quoi tout temps
                    # d'attente serait sous-évalué de `min_presence` secondes).
                    dwell = round(t_exit - t0, 1)
                    # Une présence jamais confirmée n'a jamais « eu lieu » : aucun
                    # ZONE_DWELL pour un passant. DWELL_MIN_SECONDS reste le plancher
                    # quand la zone est en comptage immédiat (min_presence = 0).
                    if dwell >= max(min_presence, self._dwell_min_s):
                        event_dispatch.dispatch(
                            self.camera_id, "ZONE_DWELL",
                            meta={"zone_id": zid, "zone_name": z.get("name"),
                                  "kind": z.get("kind"), "dwell_s": dwell},
                        )

            # ── Verrou de CONFIRMATION : qui est RÉELLEMENT « dans » la zone ──
            # (a) Les tracks VUS sur cette frame, présents SANS INTERRUPTION depuis
            # `min_presence`. Un passant, ou un arrêt d'une à deux secondes, ne
            # gonfle donc plus l'occupation et ne peut plus déclencher de faux
            # attroupement (CROWD_MIN_SECONDS ne regarde que le compte AGRÉGÉ : un
            # flux continu de passants différents le maintenait au-dessus du seuil
            # sans que personne ne s'arrête).
            # `set(...)` et non `members` : le |= ci-dessous muterait sinon
            # l'ensemble déjà rangé dans self._zone_members[zid].
            if min_presence <= 0.0:
                confirmed = set(members)                 # comptage immédiat (intrusion)
            else:
                confirmed = {tid for tid in members
                             if (now - entry.get(tid, now)) >= min_presence}
            # (b) Les tracks EN DÉLAI DE GRÂCE : disparus, mais dont la sortie n'est
            # pas encore confirmée. Le chronomètre d'attente les considère toujours
            # présents ; l'occupation doit dire la même chose, sans quoi une
            # occlusion vide la zone — historique en dents de scie, et surtout
            # compte à rebours d'attroupement remis à zéro (CROWD_MIN_SECONDS)
            # précisément quand la scène est dense et que les gens se masquent.
            # Le critère est évalué à l'instant de la DISPARITION (t_exit) et non
            # maintenant : sinon un passant occulté finirait par « mûrir » en
            # présent au seul écoulement du temps, sans avoir jamais été confirmé.
            confirmed |= {tid for tid, t_exit in pending.items()
                          if tid in entry and (t_exit - entry[tid]) >= min_presence}

            # Occupation LISSÉE : médiane des comptages CONFIRMÉS de la fenêtre.
            # Coupe les pics d'une frame (raté de détection, faux positif fugace)
            # qui partaient sinon en base et polluaient toutes les stats en aval.
            count = self._smoothed_count(zid, len(confirmed), now)

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
                if t.get("predicted"):
                    continue         # position MAINTENUE → aucune bascule de côté
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
            # (Aucune purge ici : elle se fait par TTL, cf. _purge_stale_tracks.)

    # ── Utilitaires d'état ──────────────────────────────────────────────────
    def _min_presence(self, z: Dict) -> float:
        """Délai de confirmation (s) applicable à CETTE zone.

        Priorité : réglage propre à la zone (`min_presence_s`), sinon défaut Core
        (ZONE_MIN_PRESENCE_SECONDS). 0 = comptage immédiat, à réserver aux zones
        d'intrusion. Une valeur absente, illisible ou négative retombe sur le
        défaut : mieux vaut appliquer le verrou que le désarmer en silence.
        """
        raw = z.get("min_presence_s")
        if raw is None:
            return self._zone_min_presence
        try:
            v = float(raw)
        except (TypeError, ValueError):
            return self._zone_min_presence
        return v if v >= 0.0 else self._zone_min_presence

    def _smoothed_count(self, zone_id: int, raw_count: int, now: float) -> int:
        """Occupation lissée : médiane des comptages bruts sur OCCUPANCY_SMOOTH_SECONDS."""
        if self._occ_smooth_s <= 0:
            return raw_count
        win = self._occ_window.setdefault(zone_id, deque())
        win.append((now, raw_count))
        cutoff = now - self._occ_smooth_s
        while win and win[0][0] < cutoff:
            win.popleft()
        vals = sorted(c for _, c in win)
        return vals[len(vals) // 2] if vals else raw_count

    def _purge_stale_tracks(self) -> None:
        """Oublie l'état des tracks absents depuis plus de TRACK_STATE_TTL_FRAMES
        (borne mémoire), tout en le conservant assez longtemps pour qu'une
        disparition brève ne réinitialise ni l'âge ni le côté engagé d'un track."""
        stale = [tid for tid, seen in self._track_last_seen.items()
                 if (self._frame_no - seen) > self._state_ttl]
        for tid in stale:
            self._track_last_seen.pop(tid, None)
            self._track_age.pop(tid, None)
            for committed in self._line_committed.values():
                committed.pop(tid, None)
            for last_cross in self._line_last_cross.values():
                last_cross.pop(tid, None)

    def zones_for_point(self, x: float, y: float) -> List[int]:
        """Ids des zones contenant le point (normalisé) — enrichit le Scene Model."""
        out = []
        for z in self.zones:
            poly = z.get("polygon") or []
            if poly and point_in_polygon(x, y, poly):
                out.append(z.get("id"))
        return out

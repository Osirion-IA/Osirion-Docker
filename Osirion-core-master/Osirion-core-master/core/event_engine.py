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
import os
import time
from collections import deque
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

from core.geometry import bbox_polygon_overlap_ratio, point_in_polygon, segment_side
from core import event_dispatch
from services.zones_fetching_service import fetch_zones, fetch_lines
from utils.logger import get_logger

logger = get_logger(__name__)

# Type de zone « exclusion » : ne produit AUCUN événement ; toute détection dont le
# point au sol y tombe est jetée avant le tracking (décor trompeur).
ZONE_IGNORE = "ignore"
# Poste de travail surveillé : occupation suivie PENDANT LES CRÉNEAUX TRAVAILLÉS
# du régime horaire lié, pour repérer les absences. Ces zones n'émettent QUE
# POST_VACANT / POST_ABSENCE : ni occupation, ni attroupement, ni temps de
# présence — un poste est occupé ou vide, le reste ne serait que du volume.
ZONE_PRESENCE = "presence"


class EventEngine:
    def __init__(self, camera_id: int, config, staffing_policy: Optional[Dict] = None):
        self.camera_id = camera_id
        self.config = config
        self.zones: List[Dict] = []        # zones ANALYTIQUES (hors exclusion)
        self.lines: List[Dict] = []
        self._ignore_polygons: List[List] = []   # polygones des zones d'exclusion actives
        # Enveloppe d'INTÉRÊT : rectangles normalisés (x0,y0,x1,y1) couvrant les
        # zones et les lignes actives, dilatés d'une marge. Sert à écarter du
        # tracker les détections qui ne concerneront jamais un comptage.
        self._interest_boxes: List[tuple] = []
        # Marge de dilatation, en fraction de l'image. 0 = filtre désactivé.
        # Généreuse par défaut : rater une vraie personne coûte bien plus cher
        # que suivre un passant de trop.
        self._interest_margin = max(0.0, float(
            os.getenv("TRACK_ZONE_GATE_MARGIN", "0.08") or 0.0
        ))

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
        # Tolérance d'absence de REPLI (s) — la vraie valeur vient du régime
        # horaire de la zone ; celle-ci ne sert que si le régime n'en porte pas.
        self._post_tolerance_default = float(
            getattr(config, "POST_ABSENCE_TOLERANCE_SECONDS", 600.0)
        )
        self._presence_overlap_min = max(
            0.0,
            min(1.0, float(getattr(config, "PRESENCE_BBOX_OVERLAP_MIN", 0.50))),
        )
        self._presence_candidate_grace_s = max(
            0.0,
            float(getattr(config, "PRESENCE_CANDIDATE_GRACE_SECONDS", 5.0)),
        )
        self._presence_audit_interval_s = max(
            0.0,
            float(getattr(config, "PRESENCE_AUDIT_INTERVAL_SECONDS", 0.0)),
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
        # Présence aux postes, par zone : {"vacant_since", "reported", "in_work"}.
        self._post_state: Dict[int, Dict] = {}
        # Dernier échantillon de contrôle par zone. Ce flux est séparé des alertes
        # métier et n'est actif que durant une campagne explicite (intervalle > 0).
        self._presence_audit_last: Dict[int, float] = {}
        # Le rafraîchisseur peut clôturer une zone supprimée/désactivée pendant
        # que le thread caméra traite une frame : sérialise ces rares mutations.
        self._post_lock = threading.Lock()
        # Disponibilité de la chaîne vidéo. Une coupure caméra est un état métier
        # distinct d'un poste vide : elle suspend les chronos et les décisions.
        self._monitoring_lock = threading.Lock()
        self._monitoring_available = False
        self._monitoring_reason = "initializing"
        self._monitoring_changed_at = time.time()
        # Régimes déjà signalés comme illisibles (journalisation une seule fois).
        self._sched_warned: set = set()
        # Effectif global : politique caméra + épisode de sous-effectif. Le verrou
        # protège les mises à jour à chaud envoyées par la supervision caméra.
        self._staffing_lock = threading.Lock()
        self._staffing_state: Dict = {
            "low_since": None,
            "reported": False,
            "in_work": False,
            "last_count": 0,
        }
        self._staffing_policy = self._prepare_staffing_policy(staffing_policy)

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

    def has_presence_zones(self) -> bool:
        """Vrai si cette caméra porte au moins une zone de poste active."""
        return any(
            z.get("kind") == ZONE_PRESENCE and z.get("is_active", True)
            for z in self.zones
        )

    def update_camera_health(
        self, camera_state: str, now: Optional[float] = None
    ) -> None:
        """Injecte la santé vidéo dans la décision de présence.

        Une caméra non ``online`` ne signifie jamais « personne détectée ». Les
        épisodes ouverts sont clôturés à l'instant de la coupure afin que le temps
        hors signal ne gonfle ni les absences ni le sous-effectif.
        """
        now = time.time() if now is None else float(now)
        available = camera_state == "online"
        with self._monitoring_lock:
            changed = available != self._monitoring_available
            if changed:
                self._monitoring_available = available
                self._monitoring_changed_at = now
            self._monitoring_reason = None if available else (camera_state or "unknown")

        if available:
            return

        # Réessayé à chaque contrôle de santé si le dispatcher était saturé.
        with self._post_lock:
            for zid, st in self._post_state.items():
                if self._close_post_episode(
                    zid, st, now, reason="camera_unavailable"
                ):
                    st["in_work"] = False
        with self._staffing_lock:
            if self._close_staffing_episode(
                now, self._staffing_state.get("last_count", 0),
                "camera_unavailable",
            ):
                self._staffing_state["in_work"] = False

    def _mark_frame_available(self, now: float) -> None:
        """Une frame fraîche constitue la preuve la plus directe de disponibilité."""
        with self._monitoring_lock:
            if not self._monitoring_available:
                self._monitoring_changed_at = now
            self._monitoring_available = True
            self._monitoring_reason = None

    def monitoring_snapshot(self) -> Dict:
        with self._monitoring_lock:
            return {
                "available": self._monitoring_available,
                "state": "online" if self._monitoring_available else "unavailable",
                "reason": self._monitoring_reason,
                "changed_at": self._monitoring_changed_at,
            }

    def presence_snapshot(self, now: Optional[float] = None) -> List[Dict]:
        """État décisionnel explicite de chaque zone ``presence``."""
        now = time.time() if now is None else float(now)
        monitoring = self.monitoring_snapshot()
        zones = [
            z for z in self.zones
            if z.get("kind") == ZONE_PRESENCE and z.get("is_active", True)
        ]
        result = []
        with self._post_lock:
            for zone in zones:
                zid = zone.get("id")
                sched = zone.get("_sched")
                st = self._post_state.get(zid) or {}
                evidence = st.get("last_evidence") or {}
                in_schedule = bool(sched and self._in_work_segment(sched, now))
                vacant_since = st.get("vacant_since")
                vacant_for = (
                    max(0.0, now - vacant_since)
                    if vacant_since is not None and in_schedule else None
                )
                candidate_at = st.get("last_candidate_at")
                candidate_grace = bool(
                    candidate_at is not None
                    and (now - candidate_at) <= self._presence_candidate_grace_s
                )

                if not monitoring["available"]:
                    state = "unavailable"
                elif not sched:
                    state = "unconfigured"
                elif not in_schedule:
                    state = "off_schedule"
                elif evidence.get("decision_state") == "occupied":
                    state = "occupied"
                elif (
                    evidence.get("decision_state") == "presence_pending"
                    or candidate_grace
                ):
                    state = "confirming"
                elif st.get("reported"):
                    state = "vacant"
                elif vacant_since is not None:
                    state = "vacancy_pending"
                else:
                    state = "initializing"

                tolerance = float(sched["tol"]) if sched else None
                result.append({
                    "zone_id": zid,
                    "zone_name": zone.get("name"),
                    "work_schedule_id": zone.get("work_schedule_id"),
                    "work_schedule_name": sched.get("name") if sched else None,
                    # Géométrie normalisée : consommée par l'overlay de contrôle
                    # terrain. Elle permet de vérifier visuellement qu'un agent
                    # se trouve réellement dans le périmètre évalué.
                    "polygon": zone.get("polygon") or [],
                    "state": state,
                    "in_work": in_schedule,
                    "monitoring_available": monitoring["available"],
                    "monitoring_reason": monitoring["reason"],
                    "confirmed_count": int(evidence.get("confirmed_count") or 0),
                    "candidate_count": int(evidence.get("candidate_count") or 0),
                    "min_presence_s": self._min_presence(zone),
                    "vacant_since": vacant_since,
                    "vacant_for_s": round(vacant_for, 1) if vacant_for is not None else None,
                    "absence_tolerance_s": tolerance,
                    "alert_in_s": (
                        round(max(0.0, tolerance - vacant_for), 1)
                        if tolerance is not None and vacant_for is not None
                        else None
                    ),
                    "alert_active": bool(st.get("reported")),
                    "updated_at": st.get("last_decision_at"),
                    # Signaux de diagnostic volontairement compacts. Les boîtes
                    # individuelles restent dans les métadonnées d'événement ; le
                    # flux live n'a besoin que des agrégats utiles à la calibration.
                    "membership_mode": evidence.get("membership_mode"),
                    "bbox_overlap_threshold": evidence.get("bbox_overlap_threshold"),
                    "inference_imgsz": evidence.get("inference_imgsz"),
                    "frame_person_detections": int(
                        evidence.get("frame_person_detections") or 0
                    ),
                    "frame_max_confidence": round(
                        float(evidence.get("frame_max_confidence") or 0.0), 4
                    ),
                })
        return result

    def _reload(self) -> None:
        try:
            zones_recues = fetch_zones(self.camera_id)
            if zones_recues is not None:
                # Construit d'abord les nouvelles références, puis les échange : le
                # thread caméra voit l'ancienne ou la nouvelle config, jamais une
                # liste à moitié préparée.
                ignore_polygons = [
                    z.get("polygon") for z in zones_recues
                    if z.get("kind") == ZONE_IGNORE and z.get("is_active", True)
                    and (z.get("polygon") or [])
                ]
                zones = [
                    z for z in zones_recues
                    if z.get("kind") != ZONE_IGNORE and z.get("is_active", True)
                ]
                # Régimes horaires PRÉ-PARSÉS ici (toutes les 30 s), pas dans la boucle
                # caméra : convertir « HH:MM » et instancier un ZoneInfo à chaque frame
                # et pour chaque zone serait du gaspillage pur.
                for z in zones:
                    if z.get("kind") == ZONE_PRESENCE:
                        z["_sched"] = self._prepare_schedule(z.get("schedule"))

                # Une zone supprimée/inactive, ou un régime désactivé, clôt l'épisode
                # ouvert. Sans cette réconciliation, l'analytique l'afficherait
                # indéfiniment comme « vacant maintenant ».
                monitored_post_ids = {
                    z.get("id") for z in zones
                    if z.get("kind") == ZONE_PRESENCE and z.get("_sched")
                }
                self._reconcile_post_states(monitored_post_ids, time.time())
                self._ignore_polygons = ignore_polygons
                self.zones = zones
                self._interest_boxes = self._build_interest_boxes(zones, self.lines)

            lignes_recues = fetch_lines(self.camera_id)
            if lignes_recues is not None:
                self.lines = [ln for ln in lignes_recues if ln.get("is_active", True)]
                # Les lignes arrivent après les zones : on reconstruit l'enveloppe
                # pour qu'elle les englobe aussi.
                self._interest_boxes = self._build_interest_boxes(self.zones, self.lines)
        except Exception as e:
            logger.debug(f"[event-engine cam={self.camera_id}] reload KO : {e}")

    # ── Filtrage amont (appelé par le thread caméra, avant le tracking) ─────
    def _build_interest_boxes(self, zones: List, lines: List) -> List[tuple]:
        """Rectangles normalisés couvrant zones et lignes, dilatés de la marge.

        On prend la BOÎTE ENGLOBANTE de chaque polygone, pas le polygone lui-même :
        c'est volontairement permissif. Le but n'est pas de décider qui compte —
        l'Event Engine le fait ensuite au point au sol — mais d'écarter ce qui ne
        pourra jamais compter, par exemple un passant à l'autre bout du champ.
        """
        m = self._interest_margin
        if m <= 0:
            return []                       # filtre désactivé
        boxes: List[tuple] = []
        for z in zones or []:
            poly = z.get("polygon") or []
            if len(poly) < 3:
                continue
            xs = [float(pt[0]) for pt in poly]
            ys = [float(pt[1]) for pt in poly]
            boxes.append((min(xs) - m, min(ys) - m, max(xs) + m, max(ys) + m))
        for ln in lines or []:
            a, b = ln.get("point_a") or [], ln.get("point_b") or []
            if len(a) < 2 or len(b) < 2:
                continue
            # Une ligne se franchit : les gens arrivent DES DEUX CÔTÉS. On double
            # la marge, sans quoi on perdrait l'approche et donc le comptage.
            lm = m * 2
            boxes.append((min(a[0], b[0]) - lm, min(a[1], b[1]) - lm,
                          max(a[0], b[0]) + lm, max(a[1], b[1]) + lm))
        return boxes

    def filter_outside_interest(self, boxes: List, frame_w: int, frame_h: int) -> List:
        """Retire les détections hors de toute zone ou ligne configurée.

        Appelé AVANT le tracker : une personne qui traverse le champ sans jamais
        approcher d'une zone ne devient pas un track. L'association OC-SORT est
        quadratique — mesuré sur ce parc : 31 ms pour 5 personnes, 117 ms pour 15,
        853 ms pour 60, quand la passe YOLO en coûte 360. Chaque track évité
        rapporte plus que le précédent.

        Garde-fou : SANS enveloppe (filtre désactivé, ou caméra sans aucune zone
        ni ligne), on ne filtre rien. Il vaut mieux suivre tout le monde que
        rendre une caméra aveugle sur une configuration incomplète.
        """
        envs = self._interest_boxes             # référence locale (swap atomique)
        if not envs or not boxes or not frame_w or not frame_h:
            return boxes
        kept = []
        for b in boxes:
            fx = ((b[0] + b[2]) / 2.0) / frame_w
            fy = b[3] / frame_h                 # point au sol, comme filter_ignored
            for (x0, y0, x1, y1) in envs:
                if x0 <= fx <= x1 and y0 <= fy <= y1:
                    kept.append(b)
                    break
        return kept

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

    def _presence_members(self, tracks_norm: List[Dict], poly: List) -> Tuple[set, List[Dict]]:
        """Tracks appartenant à un poste + preuves géométriques de la décision.

        Les autres zones utilisent exclusivement le point au sol. Pour un poste,
        on accepte aussi une boîte dont une part importante recouvre le polygone :
        un agent assis derrière un comptoir a souvent les pieds masqués ou hors
        champ alors que 70–95 % de son corps se trouve bien dans la zone.
        """
        members = set()
        evidence = []
        for track in tracks_norm:
            foot_inside = point_in_polygon(track["x"], track["y"], poly)
            overlap = bbox_polygon_overlap_ratio(track.get("bbox") or [], poly)
            via_overlap = overlap >= self._presence_overlap_min
            if not (foot_inside or via_overlap):
                continue
            members.add(track["track_id"])
            evidence.append({
                "track_id": track["track_id"],
                "confidence": round(float(track.get("confidence") or 0.0), 4),
                "overlap": round(overlap, 4),
                "foot_inside": bool(foot_inside),
                "predicted": bool(track.get("predicted")),
                "membership": "foot" if foot_inside else "bbox_overlap",
            })
        return members, evidence

    # ── Traitement d'une frame (thread caméra) ──────────────────────────────
    def process(self, tracks_norm: List[Dict], frame=None,
                detection_context: Optional[Dict] = None) -> None:
        """tracks_norm : [{'track_id', 'x', 'y', 'bbox', 'confidence', 'predicted'}]
        avec (x, y) = point au sol NORMALISÉ dans [0,1] et `predicted` = position
        MAINTENUE (track en sursis, non observé sur cette frame). Émet les événements
        (fire-and-forget)."""
        now = time.time()
        self._mark_frame_available(now)
        detection_context = detection_context or {}
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

        # Effectif caméra = UNION des tracks confirmés dans les zones `presence`.
        # Un même agent dans deux zones qui se chevauchent ne compte qu'une fois.
        staffing_members = set()
        staffing_zone_count = 0

        # ── Occupation + attroupement ──
        for z in zones:
            if not z.get("is_active", True):
                continue
            zid = z.get("id")
            poly = z.get("polygon") or []
            if not poly:
                continue
            est_presence = z.get("kind") == ZONE_PRESENCE
            # Appartenance GÉOMÉTRIQUE (brute) : les zones ordinaires restent au
            # point au sol ; un poste accepte aussi un fort recouvrement corps/zone
            # (pieds masqués par un comptoir ou coupés par le bord de l'image).
            if est_presence:
                members, presence_evidence = self._presence_members(tracks_norm, poly)
            else:
                members = {
                    t["track_id"] for t in tracks_norm
                    if point_in_polygon(t["x"], t["y"], poly)
                }
                presence_evidence = []

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
                    # Rien non plus pour un poste : la métrique y est l'ABSENCE, pas
                    # la durée des présences continues de l'agent.
                    if not est_presence and dwell >= max(min_presence, self._dwell_min_s):
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

            # ── Poste de travail : on ne suit que l'absence ──
            # Une zone `presence` n'émet ni occupation ni attroupement : un poste
            # est occupé ou vide, publier son compte à chaque changement ne serait
            # que du volume en base pour une information déjà portée par les
            # épisodes d'absence.
            if est_presence:
                staffing_zone_count += 1
                staffing_members.update(confirmed)
                provisional_ids = members - confirmed
                raw_candidates = []
                for index, detection in enumerate(
                    detection_context.get("person_detections") or []
                ):
                    bbox = detection.get("bbox")
                    if not bbox or len(bbox) < 4:
                        continue
                    raw_track = {
                        "track_id": f"detection:{index}",
                        "x": (float(bbox[0]) + float(bbox[2])) / 2.0,
                        "y": float(bbox[3]),
                        "bbox": bbox,
                        "confidence": detection.get("confidence", 0.0),
                        "predicted": False,
                    }
                    raw_ids, raw_evidence = self._presence_members([raw_track], poly)
                    if raw_ids:
                        for item in raw_evidence:
                            item["source"] = "raw_detection"
                        raw_candidates.extend(raw_evidence)
                has_candidate = bool(provisional_ids or raw_candidates)
                # Le même humain apparaît généralement dans le tracker ET dans
                # les détections brutes. Additionner les deux gonflait la preuve
                # affichée (p. ex. 11 candidats pour 7 personnes). Sans association
                # géométrique coûteuse supplémentaire, le maximum des deux sources
                # est l'estimation compacte la moins trompeuse.
                candidate_count = max(len(provisional_ids), len(raw_candidates))
                zone_evidence = {
                    "decision_state": (
                        "occupied" if count > 0
                        else ("presence_pending" if has_candidate else "vacant")
                    ),
                    "confirmed_count": len(confirmed),
                    "candidate_count": candidate_count,
                    "tracked_candidate_count": len(provisional_ids),
                    "raw_candidate_count": len(raw_candidates),
                    "membership_mode": "foot_or_bbox_overlap",
                    "bbox_overlap_threshold": self._presence_overlap_min,
                    "zone_tracks": presence_evidence + raw_candidates,
                    "inference_imgsz": detection_context.get("inference_imgsz"),
                    "frame_person_detections": detection_context.get(
                        "person_detection_count", 0
                    ),
                    "frame_max_confidence": detection_context.get(
                        "max_detection_confidence", 0.0
                    ),
                }
                self._process_post(
                    z, zid, now,
                    occupe=(count > 0),
                    provisional=(count == 0 and has_candidate),
                    evidence=zone_evidence,
                    frame=frame,
                )
                self._maybe_emit_presence_audit(
                    z, zid, now, zone_evidence, frame
                )
                continue

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

        self._process_staffing(
            now,
            count=len(staffing_members),
            has_presence_zones=(staffing_zone_count > 0),
            frame=frame,
        )

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

    # ── Présence au poste ───────────────────────────────────────────────────
    def _maybe_emit_presence_audit(
        self, z: Dict, zid: int, now: float,
        evidence: Optional[Dict], frame=None,
    ) -> bool:
        """Échantillonne l'état d'un poste pour l'évaluation hors-ligne.

        Les seuls POST_VACANT ne permettent pas de mesurer les faux négatifs :
        lorsque le moteur ne déclenche rien, il faut tout de même disposer de
        quelques images de vérité terrain. L'échantillon reste peu fréquent,
        limité aux horaires travaillés et désactivé par défaut.
        """
        interval = self._presence_audit_interval_s
        sched = z.get("_sched")
        if (
            interval <= 0.0
            or frame is None
            or not sched
            or not self._in_work_segment(sched, now)
        ):
            return False

        last = self._presence_audit_last.get(zid)
        if last is not None and (now - last) < interval:
            return False

        snapshot = next(
            (item for item in self.presence_snapshot(now) if item.get("zone_id") == zid),
            None,
        ) or {}
        decision = dict(evidence or {})
        slot = int(now // interval)
        queued = event_dispatch.dispatch(
            self.camera_id,
            "PRESENCE_AUDIT_SAMPLE",
            meta={
                "zone_id": zid,
                "zone_name": z.get("name"),
                "schedule_id": sched.get("id"),
                "schedule_name": sched.get("name"),
                "audit_schema_version": 1,
                "presence_schema_version": 2,
                "presence_data_quality": "audit",
                "audit_interval_s": interval,
                "event_uid": f"presence-audit:{self.camera_id}:{zid}:{slot}",
                "state": snapshot.get("state"),
                "in_work": snapshot.get("in_work"),
                "monitoring_available": snapshot.get("monitoring_available"),
                "confirmed_count": snapshot.get("confirmed_count", 0),
                "candidate_count": snapshot.get("candidate_count", 0),
                "vacant_for_s": snapshot.get("vacant_for_s"),
                "alert_active": snapshot.get("alert_active", False),
                "polygon": snapshot.get("polygon") or z.get("polygon") or [],
                "decision": decision,
            },
            frame=frame,
            confidence=float(decision.get("frame_max_confidence") or 0.0),
        )
        if queued is not False:
            self._presence_audit_last[zid] = now
            return True
        return False

    def _process_post(
        self, z: Dict, zid: int, now: float, occupe: bool,
        provisional: bool = False, evidence: Optional[Dict] = None, frame=None,
    ) -> None:
        """Suit l'occupation d'un poste et signale ses absences.

        Deux événements complémentaires :
          POST_VACANT  — signal TEMPS RÉEL : le poste est vide depuis la tolérance
                         (avec photo à l'appui). C'est lui qu'une alerte écoute.
          POST_ABSENCE — épisode CLOS, avec sa durée totale : c'est lui qui sert à
                         cumuler le temps d'absence d'une journée.

        Rien n'est émis hors des créneaux travaillés : un poste vide la nuit ou le
        dimanche n'est pas une absence, et l'écrire en base serait du volume pur.
        """
        with self._post_lock:
            self._process_post_locked(
                z, zid, now, occupe, provisional, evidence or {}, frame
            )

    def _process_post_locked(
        self, z: Dict, zid: int, now: float, occupe: bool,
        provisional: bool = False, evidence: Optional[Dict] = None, frame=None,
    ) -> None:
        """Implémentation sous ``_post_lock`` (thread caméra + rafraîchisseur)."""
        sched = z.get("_sched")
        st = self._post_state.get(zid)
        if not sched:
            # Aucun régime, régime désactivé ou illisible → surveillance suspendue,
            # mais un épisode déjà signalé doit d'abord être clôturé.
            if st is not None and self._close_post_episode(
                zid, st, now, reason="monitoring_suspended", frame=frame
            ):
                self._post_state.pop(zid, None)
            return

        dans_creneau = self._in_work_segment(sched, now)
        if st is not None and st.get("schedule_id") != sched["id"]:
            # Réaffecter un poste à un autre régime coupe proprement l'ancien
            # épisode ; le nouveau régime repart de l'instant de bascule.
            if not self._close_post_episode(
                zid, st, now, reason="schedule_changed", frame=frame
            ):
                return
            st["in_work"] = False

        st = self._post_state.setdefault(
            zid,
            {
                "vacant_since": None,
                "reported": False,
                "in_work": False,
                "last_candidate_at": None,
                "last_evidence": {},
                "opening_frame": None,
            },
        )
        evidence = evidence or {}
        st.update(
            zone_name=z.get("name"),
            schedule_id=sched["id"],
            schedule_name=sched["name"],
            last_evidence=evidence,
            last_decision_at=now,
        )

        if not dans_creneau:
            # Fin de créneau (pause, fermeture) : une absence en cours se clôt ICI.
            # Sans cela elle resterait ouverte jusqu'au lendemain et le cumul
            # journalier compterait la nuit entière comme du temps d'absence.
            if st["in_work"]:
                if self._close_post_episode(
                    zid, st, now, reason="schedule_ended", frame=frame
                ):
                    st["in_work"] = False
            return

        if not st["in_work"]:
            # Entrée dans un créneau : état propre. Un poste vide à l'ouverture
            # commence à compter maintenant, pas depuis la veille.
            st.update(
                vacant_since=(None if occupe else now),
                reported=False,
                in_work=True,
                last_candidate_at=(now if provisional else None),
                opening_frame=None,
            )
            return

        if occupe:
            self._close_post_episode(
                zid, st, now, reason="presence_restored", frame=frame
            )  # l'agent est là (ou revenu)
            return

        if st["vacant_since"] is None:
            st["vacant_since"] = now

        # Une personne est géométriquement dans la zone mais n'a pas encore tenu
        # `min_presence_s`. Le poste n'est pas déclaré occupé, toutefois émettre
        # maintenant produirait exactement les captures contradictoires observées
        # le 26/08. Le chrono de vacance continue (un passant ne le remet pas à
        # zéro), mais le signal attend que la scène redevienne vide ou que la
        # présence soit confirmée.
        if provisional:
            st["last_candidate_at"] = now
            return

        # L'alternance 640/960 peut perdre momentanément une posture difficile à
        # une échelle alors qu'elle vient d'être vue à l'autre. Une courte grâce
        # empêche l'alerte de tomber exactement dans cet intervalle. Le chrono de
        # vacance n'est toujours pas remis à zéro : si le candidat était un simple
        # passant, l'alerte part dès que cette grâce est écoulée.
        last_candidate_at = st.get("last_candidate_at")
        if (
            last_candidate_at is not None
            and (now - last_candidate_at) <= self._presence_candidate_grace_s
        ):
            return

        if not st["reported"] and (now - st["vacant_since"]) >= sched["tol"]:
            episode_id = f"{self.camera_id}:{zid}:{int(st['vacant_since'] * 1000)}"
            decision = dict(evidence)
            decision["last_candidate_age_s"] = (
                round(max(0.0, now - last_candidate_at), 1)
                if last_candidate_at is not None else None
            )
            decision["candidate_grace_s"] = self._presence_candidate_grace_s
            queued = event_dispatch.dispatch(
                self.camera_id, "POST_VACANT",
                meta={"zone_id": zid, "zone_name": z.get("name"),
                      "schedule_id": sched["id"], "schedule_name": sched["name"],
                      "presence_schema_version": 2,
                      "presence_data_quality": "reliable",
                      "vacant_s": round(now - st["vacant_since"], 1),
                      "episode_id": episode_id,
                      "event_uid": f"post-vacant:{episode_id}",
                      "decision": decision},
                frame=frame,    # photo du poste vide : la preuve, pas l'accusation
                critical=True,
            )
            # File pleine ou dispatcher non démarré : on reste non signalé et la
            # prochaine frame retentera, au lieu de perdre définitivement l'alerte.
            if queued is not False:
                st["reported"] = True
                # Une clôture provoquée sans frame fraîche (caméra coupée,
                # configuration retirée) conserve malgré tout une preuve visuelle.
                # La copie évite que le buffer vidéo soit réutilisé avant l'envoi.
                st["opening_frame"] = (
                    frame.copy() if hasattr(frame, "copy") else frame
                ) if frame is not None else None

    def _close_post_episode(
        self, zid: int, st: Dict, fin: float,
        reason: str = "monitoring_ended",
        frame=None,
    ) -> bool:
        """Clôt un épisode signalé ; renvoie False si la file locale est pleine."""
        if st.get("reported") and st.get("vacant_since") is not None:
            episode_id = f"{self.camera_id}:{zid}:{int(st['vacant_since'] * 1000)}"
            opening_frame = st.get("opening_frame")
            snapshot_frame = frame if frame is not None else opening_frame
            snapshot_origin = (
                "closure_frame" if frame is not None
                else ("vacancy_frame_fallback" if opening_frame is not None else "none")
            )
            queued = event_dispatch.dispatch(
                self.camera_id,
                "POST_ABSENCE",
                meta={
                    "zone_id": zid,
                    "zone_name": st.get("zone_name"),
                    "schedule_id": st.get("schedule_id"),
                    "schedule_name": st.get("schedule_name"),
                    "presence_schema_version": 2,
                    # La durée d'absence n'est exploitable en analyse métier que si
                    # l'épisode s'est terminé par le RETOUR OBSERVÉ d'un agent. Clos
                    # par une perte de caméra ou par la fin du créneau, il est
                    # TRONQUÉ : sa durée mesure une coupure technique, pas un
                    # comportement. Lors de la campagne d'août 2026, 44 des 74
                    # épisodes (17,2 h sur 31,8 h) étaient dans ce cas et portaient
                    # pourtant « reliable » — de quoi lire une panne vidéo comme un
                    # mauvais comportement d'agent.
                    "presence_data_quality": (
                        "reliable" if reason == "presence_restored" else "truncated"
                    ),
                    "absence_s": round(max(0.0, fin - st["vacant_since"]), 1),
                    "resolution_reason": reason,
                    "snapshot_origin": snapshot_origin,
                    "episode_id": episode_id,
                    "event_uid": f"post-absence:{episode_id}",
                },
                frame=snapshot_frame,
                critical=True,
            )
            if queued is False:
                return False
        st["vacant_since"] = None
        st["reported"] = False
        st["last_candidate_at"] = None
        st["opening_frame"] = None
        return True

    def _reconcile_post_states(self, monitored_ids: set, now: float) -> None:
        """Clôt les épisodes dont le poste n'est plus activement surveillé."""
        with self._post_lock:
            for zid in set(self._post_state) - monitored_ids:
                st = self._post_state[zid]
                if self._close_post_episode(
                    zid, st, now, reason="configuration_changed"
                ):
                    self._post_state.pop(zid, None)

    # ── Effectif global de la caméra ────────────────────────────────────────
    def _prepare_staffing_policy(self, raw: Optional[Dict]) -> Optional[Dict]:
        """Valide/prépare la politique caméra reçue du backend.

        Le backend garantit déjà les bornes. Ce second garde-fou empêche une
        configuration partielle ou ancienne de produire de fausses alertes.
        """
        if not raw:
            return None
        try:
            minimum = int(raw.get("min_agents"))
            maximum = int(raw.get("max_agents"))
            tolerance = float(raw.get("tolerance_s"))
            schedule = self._prepare_schedule(raw.get("schedule"))
        except (TypeError, ValueError):
            return None
        if not schedule or minimum < 1 or maximum < minimum or tolerance < 30:
            return None
        return {
            "camera_name": raw.get("camera_name"),
            "min": minimum,
            "max": maximum,
            "tol": tolerance,
            "schedule": schedule,
            "key": (minimum, maximum, tolerance, schedule["id"]),
        }

    def update_staffing_policy(self, raw: Optional[Dict], now: Optional[float] = None) -> bool:
        """Applique à chaud une politique caméra rafraîchie par la supervision.

        Un changement de seuil/régime clôt d'abord l'ancien épisode. Si la file
        locale est pleine, l'ancienne politique reste en place et le prochain
        cycle de supervision réessaiera : aucune clôture n'est perdue.
        """
        prepared = self._prepare_staffing_policy(raw)
        with self._staffing_lock:
            old = self._staffing_policy
            if (old or {}).get("key") == (prepared or {}).get("key"):
                self._staffing_policy = prepared
                return True
            if not self._close_staffing_episode(
                now if now is not None else time.time(),
                self._staffing_state.get("last_count", 0),
                "configuration_changed",
            ):
                return False
            self._staffing_state["in_work"] = False
            self._staffing_policy = prepared
            return True

    def _process_staffing(
        self, now: float, count: int, has_presence_zones: bool, frame=None
    ) -> None:
        """Ouvre/clôt un épisode lorsque l'effectif passe sous le minimum."""
        with self._staffing_lock:
            policy = self._staffing_policy
            st = self._staffing_state
            st["last_count"] = count
            st["has_presence_zones"] = bool(has_presence_zones)

            # Sans politique complète ou sans zone personnel, aucun comptage fiable.
            if not policy or not has_presence_zones:
                if self._close_staffing_episode(now, count, "monitoring_suspended"):
                    st["in_work"] = False
                return

            in_work = self._in_work_segment(policy["schedule"], now)
            if not in_work:
                if st["in_work"] and self._close_staffing_episode(
                    now, count, "schedule_ended"
                ):
                    st["in_work"] = False
                return

            if not st["in_work"]:
                st.update(
                    low_since=(now if count < policy["min"] else None),
                    reported=False,
                    in_work=True,
                    minimum=policy["min"],
                    maximum=policy["max"],
                    schedule_id=policy["schedule"]["id"],
                    schedule_name=policy["schedule"]["name"],
                    camera_name=policy.get("camera_name"),
                )
                return

            if count >= policy["min"]:
                self._close_staffing_episode(now, count, "minimum_restored")
                return

            if st.get("low_since") is None:
                st.update(
                    low_since=now,
                    minimum=policy["min"],
                    maximum=policy["max"],
                    schedule_id=policy["schedule"]["id"],
                    schedule_name=policy["schedule"]["name"],
                    camera_name=policy.get("camera_name"),
                )
            elif not st.get("reported") and (now - st["low_since"]) >= policy["tol"]:
                episode_id = (
                    f"{self.camera_id}:staffing:{int(st['low_since'] * 1000)}"
                )
                queued = event_dispatch.dispatch(
                    self.camera_id,
                    "STAFFING_LOW",
                    meta={
                        "camera_name": policy.get("camera_name"),
                        "count": count,
                        "minimum": policy["min"],
                        "maximum": policy["max"],
                        "missing": max(0, policy["min"] - count),
                        "low_s": round(now - st["low_since"], 1),
                        "schedule_id": policy["schedule"]["id"],
                        "schedule_name": policy["schedule"]["name"],
                        "episode_id": episode_id,
                        "event_uid": f"staffing-low:{episode_id}",
                    },
                    frame=frame,
                    critical=True,
                )
                if queued is not False:
                    st["reported"] = True

    def _close_staffing_episode(self, fin: float, count: int, reason: str) -> bool:
        """Clôt un sous-effectif signalé, avec sa durée et sa cause de fin."""
        st = self._staffing_state
        if st.get("reported") and st.get("low_since") is not None:
            episode_id = f"{self.camera_id}:staffing:{int(st['low_since'] * 1000)}"
            queued = event_dispatch.dispatch(
                self.camera_id,
                "STAFFING_RECOVERED",
                meta={
                    "camera_name": st.get("camera_name"),
                    "count": count,
                    "minimum": st.get("minimum"),
                    "maximum": st.get("maximum"),
                    "shortage_s": round(max(0.0, fin - st["low_since"]), 1),
                    "resolution_reason": reason,
                    "schedule_id": st.get("schedule_id"),
                    "schedule_name": st.get("schedule_name"),
                    "episode_id": episode_id,
                    "event_uid": f"staffing-recovered:{episode_id}",
                },
                critical=True,
            )
            if queued is False:
                return False
        st["low_since"] = None
        st["reported"] = False
        return True

    def staffing_snapshot(self) -> Dict:
        """État léger destiné au Scene Model temps réel du frontend."""
        monitoring = self.monitoring_snapshot()
        now = time.time()
        with self._staffing_lock:
            policy = self._staffing_policy
            st = self._staffing_state
            common = {
                "configured": bool(policy),
                "schedule_id": (
                    policy["schedule"]["id"] if policy and policy.get("schedule") else None
                ),
                "schedule_name": (
                    policy["schedule"]["name"] if policy and policy.get("schedule") else None
                ),
                "monitoring_available": monitoring["available"],
                "monitoring_state": monitoring["state"],
                "monitoring_reason": monitoring["reason"],
                "monitoring_changed_at": monitoring["changed_at"],
            }
            if not monitoring["available"]:
                return {
                    **common,
                    "enabled": bool(policy),
                    "available": bool(st.get("has_presence_zones")),
                    "decision_state": "unavailable",
                    "count": None,
                    "in_work": False,
                    "below_minimum": False,
                    "low": False,
                }
            if not policy:
                # Le comptage brut reste utile à la supervision même avant la
                # saisie des seuils. Aucun événement de sous-effectif n'est
                # toutefois produit tant que la politique caméra est absente.
                return {
                    **common,
                    "enabled": False,
                    "available": bool(st.get("has_presence_zones")),
                    "decision_state": "observing",
                    "count": st.get("last_count", 0),
                    "in_work": False,
                    "below_minimum": False,
                    "low": False,
                }
            in_work = bool(st.get("in_work"))
            count = st.get("last_count", 0)
            below = in_work and count < policy["min"]
            low_since = st.get("low_since")
            low_for = max(0.0, now - low_since) if low_since is not None else None
            decision_state = (
                "off_schedule" if not in_work
                else ("staffing_low" if st.get("reported")
                      else ("staffing_pending" if below else "staffed"))
            )
            return {
                **common,
                "enabled": True,
                "available": True,
                "decision_state": decision_state,
                "count": count,
                "minimum": policy["min"],
                "maximum": policy["max"],
                "in_work": in_work,
                "below_minimum": below,
                "low": bool(st.get("reported")),
                "low_since": low_since,
                "low_for_s": round(low_for, 1) if low_for is not None else None,
                "alert_in_s": (
                    round(max(0.0, policy["tol"] - low_for), 1)
                    if below and low_for is not None and not st.get("reported")
                    else None
                ),
            }

    # ── Régimes horaires (présence aux postes) ──────────────────────────────
    def _prepare_schedule(self, sched: Optional[Dict]) -> Optional[Dict]:
        """Convertit le régime reçu du backend en structure prête à évaluer.

        Renvoie None si le régime est absent, désactivé ou illisible : le poste
        cesse alors d'être surveillé. C'est le choix SÛR — surveiller à la
        mauvaise heure produirait des absences fantômes et, pire, disculperait de
        vraies absences. Un régime illisible est journalisé UNE fois (le
        rafraîchissement repasse toutes les 30 s, on ne veut pas inonder les logs).
        """
        if not sched:
            return None
        sid = sched.get("id")
        try:
            tz = ZoneInfo(sched.get("timezone"))
            jours: Dict[int, List[Tuple[int, int]]] = {}
            for jour, creneaux in (sched.get("segments") or {}).items():
                bornes = []
                for debut, fin in (creneaux or []):
                    hd, md = str(debut).split(":")
                    hf, mf = str(fin).split(":")
                    bornes.append((int(hd) * 60 + int(md), int(hf) * 60 + int(mf)))
                jours[int(jour)] = bornes
        except Exception as e:
            if sid not in self._sched_warned:
                self._sched_warned.add(sid)
                logger.warning(
                    f"[event-engine cam={self.camera_id}] régime horaire {sid} illisible "
                    f"({e}) → poste NON surveillé tant qu'il n'est pas corrigé."
                )
            return None
        self._sched_warned.discard(sid)
        tol = sched.get("absence_tolerance_s")
        return {
            "id": sid,
            "name": sched.get("name"),
            "tz": tz,
            "jours": jours,
            "tol": float(tol) if tol else self._post_tolerance_default,
        }

    def _in_work_segment(self, sched: Dict, now_ts: float) -> bool:
        """L'instant `now_ts` (epoch) tombe-t-il dans un créneau travaillé ?

        L'heure est évaluée dans le FUSEAU du régime : le parc est à cheval sur
        UTC+0 et UTC+1, un décalage global unique décalerait d'une heure la moitié
        des agences.
        """
        try:
            local = datetime.fromtimestamp(now_ts, sched["tz"])
        except Exception:
            return False
        minutes = local.hour * 60 + local.minute
        # weekday() : 0 = lundi — même convention que les clés du régime.
        for debut, fin in sched["jours"].get(local.weekday(), ()):
            if debut == 0 and fin == 0:  # convention : journée complète H24
                return True
            if fin > debut and debut <= minutes < fin:
                return True
            if fin < debut and minutes >= debut:  # début d'une plage de nuit
                return True
        # Seconde moitié d'une plage de nuit commencée la veille.
        previous_day = (local.weekday() - 1) % 7
        for debut, fin in sched["jours"].get(previous_day, ()):
            if fin < debut and minutes < fin:
                return True
        return False

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

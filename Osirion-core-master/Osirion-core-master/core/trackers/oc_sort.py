# core/trackers/oc_sort.py
"""
OC-SORT (Observation-Centric SORT) — implémentation AUTONOME pour Osirion.

Remplace ByteTrack (autrefois cloné depuis ifzhang/ByteTrack) par un tracker
auto-suffisant, sans dépendance Git externe. OC-SORT réduit les changements
d'identité (ID switches) sur les mouvements rapides/erratiques grâce à trois
mécanismes centrés sur l'observation :

  • OCM (Observation-Centric Momentum) : la cohérence de la DIRECTION de vitesse
    entre observations entre dans le coût d'association — un appariement
    incohérent avec la trajectoire récente est pénalisé (cf. `_associate`).
  • OCR (Observation-Centric Recovery) : une passe d'association supplémentaire
    récupère les tracks perdus en s'appuyant sur leur DERNIÈRE observation réelle
    (et, si `use_byte`, sur les détections faible confiance — esprit ByteTrack).
  • Rétention prolongée (`max_age`) : un track perdu survit plus longtemps, ce qui
    diminue les ré-créations d'ID lors d'occlusions brèves.

Filtre de Kalman : filterpy.kalman.KalmanFilter (état 7D [x, y, s, r, vx, vy, vs],
où (x, y) = centre, s = aire, r = ratio largeur/hauteur).

──────────────────────────────────────────────────────────────────────────────
ADAPTATEUR — `OCSortTrackerAdapter`
──────────────────────────────────────────────────────────────────────────────
Préserve À L'IDENTIQUE le contrat consommé par le pipeline Osirion
(core/tracking_processor.py) :

    update(output_results, img_info, img_size) -> list[objet]

    · entrée  : output_results = NumPy (N, 5) [x1, y1, x2, y2, score] (pixels frame) ;
                img_info / img_size = (hauteur, largeur). Dans Osirion ils sont
                ÉGAUX → facteur d'échelle = 1.0 (aucune remise à l'échelle).
    · sortie  : liste d'objets exposant `.track_id` (int) et `.tlwh`
                (x, y, largeur, hauteur en pixels frame).

Remplaçant direct de `BYTETracker(args, frame_rate=...)` : aucun autre fichier ne
change de contrat.

Réf. : J. Cao et al., « Observation-Centric SORT: Rethinking SORT for Robust
Multi-Object Tracking », CVPR 2023.

Note d'implémentation : cette variante implémente OCM + OCR + rétention prolongée
au-dessus d'un filtre de Kalman filterpy standard. Le ré-update « rétroactif » le
long d'une trajectoire virtuelle (ORU) de l'article n'est pas reproduit ici ; les
gains principaux contre les ID switches proviennent de l'OCM et de l'OCR, tous deux
présents.
"""
from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np
from filterpy.kalman import KalmanFilter

__all__ = ["OCSortTrackerAdapter", "OCSort"]


# ──────────────────────────────────────────────────────────────────────────────
# Utilitaires géométriques (boîtes / IoU / direction de vitesse)
# ──────────────────────────────────────────────────────────────────────────────
def _iou_batch(bboxes1: np.ndarray, bboxes2: np.ndarray) -> np.ndarray:
    """IoU vectorisé entre deux jeux de boîtes [x1, y1, x2, y2]. Renvoie (N1, N2)."""
    bboxes2 = np.expand_dims(bboxes2, 0)
    bboxes1 = np.expand_dims(bboxes1, 1)
    xx1 = np.maximum(bboxes1[..., 0], bboxes2[..., 0])
    yy1 = np.maximum(bboxes1[..., 1], bboxes2[..., 1])
    xx2 = np.minimum(bboxes1[..., 2], bboxes2[..., 2])
    yy2 = np.minimum(bboxes1[..., 3], bboxes2[..., 3])
    w = np.maximum(0.0, xx2 - xx1)
    h = np.maximum(0.0, yy2 - yy1)
    wh = w * h
    area1 = (bboxes1[..., 2] - bboxes1[..., 0]) * (bboxes1[..., 3] - bboxes1[..., 1])
    area2 = (bboxes2[..., 2] - bboxes2[..., 0]) * (bboxes2[..., 3] - bboxes2[..., 1])
    return wh / (area1 + area2 - wh + 1e-12)


def _convert_bbox_to_z(bbox: np.ndarray) -> np.ndarray:
    """[x1, y1, x2, y2] → mesure Kalman [x_centre, y_centre, aire, ratio]^T (4×1)."""
    w = bbox[2] - bbox[0]
    h = bbox[3] - bbox[1]
    x = bbox[0] + w / 2.0
    y = bbox[1] + h / 2.0
    s = w * h
    r = w / float(h + 1e-6)
    return np.array([x, y, s, r], dtype=float).reshape((4, 1))


def _convert_x_to_bbox(x: np.ndarray) -> np.ndarray:
    """État Kalman → boîte [x1, y1, x2, y2] (1×4). Scalaire-sûr (pas de max() NumPy).

    `x` est l'état filterpy de forme (7, 1) → on l'aplatit pour que x[i] soit un
    vrai scalaire (float(tableau 1-élément) lève une TypeError sous NumPy ≥ 2.0 et
    émet un DeprecationWarning sous NumPy ≥ 1.25)."""
    x = np.asarray(x).reshape(-1)
    s = float(x[2])
    r = float(x[3])
    sr = s * r
    w = np.sqrt(sr) if sr > 0.0 else 0.0
    h = s / w if w > 1e-6 else 0.0
    cx, cy = float(x[0]), float(x[1])
    return np.array([cx - w / 2.0, cy - h / 2.0,
                     cx + w / 2.0, cy + h / 2.0], dtype=float).reshape((1, 4))


def _speed_direction(bbox1: np.ndarray, bbox2: np.ndarray) -> np.ndarray:
    """Direction unitaire (dy, dx) du centre de bbox1 vers celui de bbox2."""
    cx1, cy1 = (bbox1[0] + bbox1[2]) / 2.0, (bbox1[1] + bbox1[3]) / 2.0
    cx2, cy2 = (bbox2[0] + bbox2[2]) / 2.0, (bbox2[1] + bbox2[3]) / 2.0
    norm = np.sqrt((cy2 - cy1) ** 2 + (cx2 - cx1) ** 2) + 1e-6
    return np.array([(cy2 - cy1) / norm, (cx2 - cx1) / norm], dtype=float)


def _speed_direction_batch(dets: np.ndarray, tracks: np.ndarray):
    """Directions unitaires (dy, dx) entre chaque observation et chaque détection.

    Renvoie deux matrices de forme (n_tracks, n_dets)."""
    tracks = tracks[..., np.newaxis]
    cx1, cy1 = (dets[:, 0] + dets[:, 2]) / 2.0, (dets[:, 1] + dets[:, 3]) / 2.0
    cx2, cy2 = (tracks[:, 0] + tracks[:, 2]) / 2.0, (tracks[:, 1] + tracks[:, 3]) / 2.0
    dx = cx1 - cx2
    dy = cy1 - cy2
    norm = np.sqrt(dx ** 2 + dy ** 2) + 1e-6
    return dy / norm, dx / norm


def _linear_assignment(cost_matrix: np.ndarray) -> np.ndarray:
    """Affectation linéaire (Hongrois) → tableau (K, 2) de paires [ligne, colonne].

    Utilise `lap` (fourni par lapx) si disponible, sinon scipy. Renvoie (0, 2) si
    aucun appariement.
    """
    try:
        import lap
        _, x, _y = lap.lapjv(cost_matrix, extend_cost=True)
        matches = np.array([[ix, x[ix]] for ix in range(len(x)) if x[ix] >= 0])
    except ImportError:
        from scipy.optimize import linear_sum_assignment
        rows, cols = linear_sum_assignment(cost_matrix)
        matches = np.array(list(zip(rows, cols)))
    if matches.size == 0:
        return np.empty((0, 2), dtype=int)
    return matches


def _k_previous_obs(observations: Dict[int, np.ndarray], cur_age: int, k: int) -> np.ndarray:
    """Observation réelle d'il y a ~k frames (pour estimer la vitesse en OCM)."""
    if len(observations) == 0:
        return np.array([-1, -1, -1, -1, -1], dtype=float)
    for i in range(k):
        dt = k - i
        if cur_age - dt in observations:
            return observations[cur_age - dt]
    max_age = max(observations.keys())
    return observations[max_age]


def _associate(detections, trackers, iou_threshold, velocities, previous_obs, vdc_weight):
    """Association OCM : coût = IoU + cohérence de la direction de vitesse.

    Renvoie (matches (K,2) [det, trk], unmatched_dets, unmatched_trks).
    """
    if len(trackers) == 0:
        return (np.empty((0, 2), dtype=int),
                np.arange(len(detections)),
                np.empty(0, dtype=int))

    Y, X = _speed_direction_batch(detections, previous_obs)
    inertia_Y = np.repeat(velocities[:, 0][:, np.newaxis], Y.shape[1], axis=1)
    inertia_X = np.repeat(velocities[:, 1][:, np.newaxis], X.shape[1], axis=1)
    diff_angle_cos = np.clip(inertia_X * X + inertia_Y * Y, -1.0, 1.0)
    diff_angle = np.arccos(diff_angle_cos)
    diff_angle = (np.pi / 2.0 - np.abs(diff_angle)) / np.pi

    # Une observation jamais vue (marqueur -1) ne contribue pas au terme d'angle.
    valid_mask = np.ones(previous_obs.shape[0])
    valid_mask[np.where(previous_obs[:, 4] < 0)] = 0
    valid_mask = np.repeat(valid_mask[:, np.newaxis], X.shape[1], axis=1)

    iou_matrix = _iou_batch(detections, trackers)
    scores = np.repeat(detections[:, -1][:, np.newaxis], trackers.shape[0], axis=1)
    angle_diff_cost = ((valid_mask * diff_angle) * vdc_weight).T * scores

    if min(iou_matrix.shape) > 0:
        a = (iou_matrix > iou_threshold).astype(np.int32)
        if a.sum(1).max() == 1 and a.sum(0).max() == 1:
            matched_indices = np.stack(np.where(a), axis=1)
        else:
            matched_indices = _linear_assignment(-(iou_matrix + angle_diff_cost))
    else:
        matched_indices = np.empty((0, 2), dtype=int)

    unmatched_detections = [d for d in range(len(detections))
                            if d not in matched_indices[:, 0]]
    unmatched_trackers = [t for t in range(len(trackers))
                          if t not in matched_indices[:, 1]]

    # Filtre les appariements à IoU trop faible (rejetés malgré l'affectation).
    matches = []
    for m in matched_indices:
        if iou_matrix[m[0], m[1]] < iou_threshold:
            unmatched_detections.append(m[0])
            unmatched_trackers.append(m[1])
        else:
            matches.append(m.reshape(1, 2))
    matches = np.concatenate(matches, axis=0) if matches else np.empty((0, 2), dtype=int)

    return (matches,
            np.array(unmatched_detections, dtype=int),
            np.array(unmatched_trackers, dtype=int))


# ──────────────────────────────────────────────────────────────────────────────
# Track individuel (filtre de Kalman + mémoire d'observations)
# ──────────────────────────────────────────────────────────────────────────────
class KalmanBoxTracker:
    """Un track = un filtre de Kalman filterpy + l'historique de ses observations.

    L'identifiant `track_id` est attribué par l'OCSort propriétaire (compteur par
    caméra), jamais réutilisé pour la durée de vie du tracker.
    """

    def __init__(self, bbox: np.ndarray, delta_t: int = 3, track_id: int = 0):
        # État 7D : [x, y, s, r, vx, vy, vs] (position + aire + ratio + vitesses).
        self.kf = KalmanFilter(dim_x=7, dim_z=4)
        self.kf.F = np.array([
            [1, 0, 0, 0, 1, 0, 0],
            [0, 1, 0, 0, 0, 1, 0],
            [0, 0, 1, 0, 0, 0, 1],
            [0, 0, 0, 1, 0, 0, 0],
            [0, 0, 0, 0, 1, 0, 0],
            [0, 0, 0, 0, 0, 1, 0],
            [0, 0, 0, 0, 0, 0, 1],
        ], dtype=float)
        self.kf.H = np.array([
            [1, 0, 0, 0, 0, 0, 0],
            [0, 1, 0, 0, 0, 0, 0],
            [0, 0, 1, 0, 0, 0, 0],
            [0, 0, 0, 1, 0, 0, 0],
        ], dtype=float)
        self.kf.R[2:, 2:] *= 10.0
        self.kf.P[4:, 4:] *= 1000.0   # forte incertitude initiale sur les vitesses
        self.kf.P *= 10.0
        self.kf.Q[-1, -1] *= 0.01
        self.kf.Q[4:, 4:] *= 0.01
        self.kf.x[:4] = _convert_bbox_to_z(bbox)

        self.id = int(track_id)
        self.delta_t = delta_t
        self.time_since_update = 0
        self.hits = 0
        self.hit_streak = 0
        self.age = 0

        # Mémoire centrée-observation : dernière observation réelle (5D, marqueur
        # -1 = jamais observé) + historique indexé par âge (sert à l'OCM/OCR).
        self.last_observation = np.array([-1, -1, -1, -1, -1], dtype=float)
        self.observations: Dict[int, np.ndarray] = {}
        self.velocity: Optional[np.ndarray] = None

    def update(self, bbox: Optional[np.ndarray]) -> None:
        """Intègre une observation [x1, y1, x2, y2, score] ou None (track non vu)."""
        if bbox is None:
            self.kf.update(None)   # filterpy : pas de mesure → on garde la prédiction
            return

        # Vitesse centrée-observation : direction entre l'observation d'il y a
        # ~delta_t frames et l'actuelle (plus robuste au bruit frame-à-frame que
        # la vitesse instantanée du filtre).
        if self.last_observation.sum() >= 0:
            previous_box = None
            for i in range(self.delta_t):
                dt = self.delta_t - i
                if self.age - dt in self.observations:
                    previous_box = self.observations[self.age - dt]
                    break
            if previous_box is None:
                previous_box = self.last_observation
            self.velocity = _speed_direction(previous_box, bbox)

        self.last_observation = bbox
        self.observations[self.age] = bbox
        self.time_since_update = 0
        self.hits += 1
        self.hit_streak += 1
        self.kf.update(_convert_bbox_to_z(bbox))

    def predict(self) -> np.ndarray:
        """Avance le filtre d'une frame ; renvoie la boîte prédite (1×4)."""
        if (self.kf.x[6] + self.kf.x[2]) <= 0:   # aire prédite non positive → fige vs
            self.kf.x[6] *= 0.0
        self.kf.predict()
        self.age += 1
        if self.time_since_update > 0:
            self.hit_streak = 0
        self.time_since_update += 1
        return _convert_x_to_bbox(self.kf.x)

    def get_state(self) -> np.ndarray:
        """Boîte courante estimée par le filtre (1×4)."""
        return _convert_x_to_bbox(self.kf.x)


# ──────────────────────────────────────────────────────────────────────────────
# Cœur OC-SORT
# ──────────────────────────────────────────────────────────────────────────────
class OCSort:
    """Gestionnaire de tracks OC-SORT : prédiction + associations OCM/OCR (+ BYTE).

    Une instance par caméra (état non partagé → sûr en multithread : chaque caméra
    appelle update() depuis SON seul thread de traitement).
    """

    def __init__(self, det_thresh: float, max_age: int = 30, min_hits: int = 3,
                 iou_threshold: float = 0.3, delta_t: int = 3, inertia: float = 0.2,
                 use_byte: bool = True):
        self.det_thresh = det_thresh
        self.max_age = max_age
        self.min_hits = min_hits
        self.iou_threshold = iou_threshold
        self.delta_t = delta_t
        self.inertia = inertia
        self.use_byte = use_byte

        self.trackers: List[KalmanBoxTracker] = []
        self.frame_count = 0
        self._id_count = 0   # compteur d'ID propre à CETTE instance (par caméra)

    def update(self, output_results: np.ndarray, img_info, img_size) -> np.ndarray:
        """Met à jour le tracker pour la frame courante.

        Renvoie un tableau (M, 5) [x1, y1, x2, y2, track_id] en pixels frame.
        """
        if output_results is None:
            return np.empty((0, 5))

        self.frame_count += 1

        # Normalisation des détections (supporte (N,5) ou format YOLOX (N,7)).
        if output_results.shape[1] == 5:
            scores = output_results[:, 4]
            bboxes = output_results[:, :4]
        else:
            output_results = np.asarray(output_results)
            scores = output_results[:, 4] * output_results[:, 5]
            bboxes = output_results[:, :4]
        img_h, img_w = img_info[0], img_info[1]
        scale = min(img_size[0] / float(img_h), img_size[1] / float(img_w))
        bboxes = bboxes / scale   # Osirion : img_info == img_size → scale = 1.0 (no-op)
        dets = np.concatenate((bboxes, scores[:, None]), axis=1)

        remain_inds = scores > self.det_thresh
        inds_second = np.logical_and(scores > 0.1, scores < self.det_thresh)
        dets_second = dets[inds_second]   # détections faible confiance (BYTE)
        dets = dets[remain_inds]          # détections haute confiance

        # Prédiction Kalman de tous les tracks existants ; purge des NaN éventuels.
        trks = np.zeros((len(self.trackers), 5))
        to_del = []
        ret = []
        for t, trk in enumerate(trks):
            pos = self.trackers[t].predict()[0]
            trk[:] = [pos[0], pos[1], pos[2], pos[3], 0]
            if np.any(np.isnan(pos)):
                to_del.append(t)
        trks = np.ma.compress_rows(np.ma.masked_invalid(trks))
        for t in reversed(to_del):
            self.trackers.pop(t)

        velocities = np.array([
            trk.velocity if trk.velocity is not None else np.array((0.0, 0.0))
            for trk in self.trackers
        ])
        last_boxes = np.array([trk.last_observation for trk in self.trackers])
        k_observations = np.array([
            _k_previous_obs(trk.observations, trk.age, self.delta_t)
            for trk in self.trackers
        ])

        # ── 1ʳᵉ association : IoU + momentum (OCM), détections haute confiance ──
        matched, unmatched_dets, unmatched_trks = _associate(
            dets, trks, self.iou_threshold, velocities, k_observations, self.inertia
        )
        for m in matched:
            self.trackers[m[1]].update(dets[m[0], :])

        # ── 2ᵉ association (BYTE) : récupère via détections FAIBLE confiance ──
        if self.use_byte and len(dets_second) > 0 and unmatched_trks.shape[0] > 0:
            u_trks = trks[unmatched_trks]
            iou_left = _iou_batch(dets_second, u_trks)
            if iou_left.size > 0 and iou_left.max() > self.iou_threshold:
                matched_indices = _linear_assignment(-iou_left)
                to_remove = []
                for m in matched_indices:
                    det_ind, trk_ind = m[0], unmatched_trks[m[1]]
                    if iou_left[m[0], m[1]] < self.iou_threshold:
                        continue
                    self.trackers[trk_ind].update(dets_second[det_ind, :])
                    to_remove.append(trk_ind)
                unmatched_trks = np.setdiff1d(unmatched_trks, np.array(to_remove, dtype=int))

        # ── 3ᵉ association (OCR) : récupère via la DERNIÈRE observation réelle ──
        if unmatched_dets.shape[0] > 0 and unmatched_trks.shape[0] > 0:
            left_dets = dets[unmatched_dets]
            left_trks = last_boxes[unmatched_trks]
            iou_left = _iou_batch(left_dets, left_trks)
            if iou_left.size > 0 and iou_left.max() > self.iou_threshold:
                rematched = _linear_assignment(-iou_left)
                to_remove_det, to_remove_trk = [], []
                for m in rematched:
                    det_ind, trk_ind = unmatched_dets[m[0]], unmatched_trks[m[1]]
                    if iou_left[m[0], m[1]] < self.iou_threshold:
                        continue
                    self.trackers[trk_ind].update(dets[det_ind, :])
                    to_remove_det.append(det_ind)
                    to_remove_trk.append(trk_ind)
                unmatched_dets = np.setdiff1d(unmatched_dets, np.array(to_remove_det, dtype=int))
                unmatched_trks = np.setdiff1d(unmatched_trks, np.array(to_remove_trk, dtype=int))

        # Tracks toujours non appariés → on les fait « coaster » (prédiction seule).
        for m in unmatched_trks:
            self.trackers[m].update(None)

        # Nouveaux tracks pour les détections haute confiance non appariées.
        for i in unmatched_dets:
            self._id_count += 1
            trk = KalmanBoxTracker(dets[i, :], delta_t=self.delta_t, track_id=self._id_count)
            self.trackers.append(trk)

        # Construction de la sortie + purge des tracks morts (itération inversée →
        # pop par index décroissant sûr).
        i = len(self.trackers)
        for trk in reversed(self.trackers):
            if trk.last_observation.sum() < 0:
                d = trk.get_state()[0]
            else:
                # Préfère la dernière observation réelle à la prédiction Kalman.
                d = trk.last_observation[:4]
            if (trk.time_since_update < 1) and \
               (trk.hit_streak >= self.min_hits or self.frame_count <= self.min_hits):
                ret.append(np.concatenate((d, [trk.id])).reshape(1, -1))
            i -= 1
            if trk.time_since_update > self.max_age:
                self.trackers.pop(i)

        if len(ret) > 0:
            return np.concatenate(ret)
        return np.empty((0, 5))


# ──────────────────────────────────────────────────────────────────────────────
# Objet track exposé aux pipelines (contrat ByteTrack historique)
# ──────────────────────────────────────────────────────────────────────────────
class _Track:
    """Track minimal exposant exactement ce que consomment les pipelines Osirion :
    `.track_id` (int) et `.tlwh` (x, y, w, h en pixels frame). `.tlbr`/`.score`
    fournis en bonus (robustesse/avenir)."""

    __slots__ = ("track_id", "_x1", "_y1", "_x2", "_y2", "score")

    def __init__(self, track_id, x1, y1, x2, y2, score=0.0):
        self.track_id = int(track_id)
        self._x1, self._y1 = float(x1), float(y1)
        self._x2, self._y2 = float(x2), float(y2)
        self.score = float(score)

    @property
    def tlwh(self) -> np.ndarray:
        """Boîte (top-left x, top-left y, largeur, hauteur) en pixels frame."""
        return np.array([self._x1, self._y1,
                         self._x2 - self._x1, self._y2 - self._y1], dtype=float)

    @property
    def tlbr(self) -> np.ndarray:
        """Boîte (x1, y1, x2, y2) en pixels frame."""
        return np.array([self._x1, self._y1, self._x2, self._y2], dtype=float)

    def __repr__(self) -> str:
        return f"_Track(id={self.track_id}, tlwh={self.tlwh.tolist()})"


class OCSortTrackerAdapter:
    """Adaptateur OC-SORT ⇄ API ByteTrack historique d'Osirion.

    Remplaçant direct de `BYTETracker(args, frame_rate=...)`. Préserve la signature
    update(output_results, img_info, img_size) et renvoie une LISTE d'objets
    exposant `.track_id` et `.tlwh` (cf. core/tracking_processor.py:930).
    """

    def __init__(self, args, frame_rate=None):
        # `frame_rate` accepté pour compat. d'appel ByteTrack mais ignoré : OC-SORT
        # exprime la rétention directement en frames via `max_age`.
        self.tracker = OCSort(
            det_thresh=getattr(args, "det_thresh", 0.4),
            max_age=getattr(args, "max_age", 30),
            min_hits=getattr(args, "min_hits", 3),
            iou_threshold=getattr(args, "iou_threshold", 0.3),
            delta_t=getattr(args, "delta_t", 3),
            inertia=getattr(args, "inertia", 0.2),
            use_byte=getattr(args, "use_byte", True),
        )

    def update(self, output_results, img_info, img_size) -> List[_Track]:
        """Voir docstring de classe. Renvoie [] si aucune détection exploitable."""
        if output_results is None:
            return []
        output_results = np.asarray(output_results, dtype=np.float32)
        if output_results.ndim != 2 or output_results.shape[1] < 5:
            return []

        online = self.tracker.update(output_results, img_info, img_size)
        # online : (M, 5) [x1, y1, x2, y2, track_id] en pixels frame.
        return [
            _Track(int(row[4]), row[0], row[1], row[2], row[3])
            for row in online
        ]

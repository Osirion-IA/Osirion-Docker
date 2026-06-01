"""
utils/monitoring.py — Logs structurés production pour le pipeline ArcFace.

Usage :
    from utils.monitoring import emit_recognition_metric, emit_threshold_metric, \
                                  emit_cache_metric, emit_norm_drift_metric

Chaque fonction émet un log INFO structuré JSON que les outils d'agrégation
(ELK, Loki, Datadog, Grafana) peuvent parser et indexer directement.

Seuils d'alerte recommandés :
  cosine_score > 0.95          → doublon potentiel en base
  cosine_score < floor (0.35)  → vecteur bruité (frame flou non filtré ?)
  adaptive_threshold > 0.75    → trop de faux rejets → monter le plafond
  adaptive_threshold < 0.38    → trop de faux positifs → monter le plancher
  cache_hit_rate < 0.30        → surcharge API → augmenter TTL ou REIDENTIFICATION_INTERVAL
  norm_drift > 0.001           → dérive pgvector → re-normalisation à vérifier
"""

import json
import time
import logging
from typing import Optional

_monitor_logger = logging.getLogger("osirion.monitoring")


def _emit(event: str, payload: dict) -> None:
    """Émet un log structuré JSON. Compatible ELK / Loki / stdout."""
    record = {
        "ts": time.time(),
        "event": event,
        **payload
    }
    _monitor_logger.info(json.dumps(record, ensure_ascii=False))


# ─────────────────────────────────────────────────────────────
# Métriques de reconnaissance faciale
# ─────────────────────────────────────────────────────────────

def emit_recognition_metric(
    camera_id: int,
    camera_name: str,
    track_id: int,
    cosine_score: float,
    adaptive_threshold: float,
    accepted: bool,
    candidate_name: str,
    from_cache: bool = False,
) -> None:
    """
    Émettre après chaque décision de reconnaissance.

    Alertes à configurer :
      cosine_score > 0.95                  → doublon possible en base
      cosine_score < 0.35 and accepted     → faux positif probable (seuil trop bas)
      not accepted and cosine_score > 0.42 → faux rejet proche du seuil
    """
    _emit("recognition", {
        "camera_id": camera_id,
        "camera_name": camera_name,
        "track_id": track_id,
        "cosine_score": round(cosine_score, 4),
        "adaptive_threshold": round(adaptive_threshold, 4),
        "accepted": accepted,
        "candidate": candidate_name,
        "from_cache": from_cache,
        "margin": round(cosine_score - adaptive_threshold, 4),  # positif = accepté avec marge
    })


# ─────────────────────────────────────────────────────────────
# Métriques du seuil adaptatif
# ─────────────────────────────────────────────────────────────

def emit_threshold_metric(
    camera_id: int,
    camera_name: str,
    old_threshold: float,
    new_threshold: float,
    otsu_candidate: float,
    score_mean: float,
    score_std: float,
    score_min: float,
    score_max: float,
    n_samples: int,
) -> None:
    """
    Émettre à chaque recalcul Otsu du seuil adaptatif.

    Alertes à configurer :
      new_threshold > 0.75  → trop stricte → trop de "Inconnu"
      new_threshold < 0.38  → trop permissive → trop de faux positifs
      score_std < 0.05      → distribution unimodale → base trop homogène
    """
    _emit("threshold_update", {
        "camera_id": camera_id,
        "camera_name": camera_name,
        "old_threshold": round(old_threshold, 4),
        "new_threshold": round(new_threshold, 4),
        "otsu_candidate": round(otsu_candidate, 4),
        "score_mean": round(score_mean, 4),
        "score_std": round(score_std, 4),
        "score_min": round(score_min, 4),
        "score_max": round(score_max, 4),
        "n_samples": n_samples,
        "bimodal": score_std >= 0.05,  # False = distribution trop étroite pour Otsu
    })


# ─────────────────────────────────────────────────────────────
# Métriques du cache global (multi-caméra)
# ─────────────────────────────────────────────────────────────

def emit_cache_metric(
    cache_hits: int,
    cache_misses: int,
    active_persons: int,
    total_tracked: int,
) -> None:
    """
    Émettre périodiquement (ex: toutes les 100 reconnaissances).

    Alertes à configurer :
      cache_hit_rate < 0.30  → trop de re-identifications → surcharge API
      active_persons > 50    → scène très dense → vérifier TTL
    """
    total = cache_hits + cache_misses
    hit_rate = cache_hits / total if total > 0 else 0.0
    _emit("cache_stats", {
        "cache_hits": cache_hits,
        "cache_misses": cache_misses,
        "cache_hit_rate": round(hit_rate, 4),
        "active_persons": active_persons,
        "total_tracked": total_tracked,
        "alert_low_hit_rate": hit_rate < 0.30,
    })


# ─────────────────────────────────────────────────────────────
# Métriques de drift de norme (pgvector round-trip)
# ─────────────────────────────────────────────────────────────

def emit_norm_drift_metric(
    norm_min: float,
    norm_max: float,
    norm_mean: float,
    n_vectors: int,
) -> None:
    """
    Émettre au démarrage après chargement des embeddings depuis pgvector.

    Alertes à configurer :
      norm_min < 0.999  → dérive détectée → re-normalisation critique
      norm_max > 1.001  → dérive détectée → vérifier stockage pgvector
    """
    drift = norm_max - norm_min
    _emit("norm_drift", {
        "norm_min": round(norm_min, 6),
        "norm_max": round(norm_max, 6),
        "norm_mean": round(norm_mean, 6),
        "norm_drift": round(drift, 6),
        "n_vectors": n_vectors,
        "drift_detected": norm_min < 0.999 or norm_max > 1.001,
    })


# ─────────────────────────────────────────────────────────────
# Métriques du filtre qualité frame (blur)
# ─────────────────────────────────────────────────────────────

def emit_blur_metric(
    camera_id: int,
    camera_name: str,
    sharpness: float,
    threshold: float,
    total_skipped: int,
) -> None:
    """
    Émettre à chaque frame rejetée pour flou (cadence réduite par l'appelant).

    Alertes à configurer :
      total_skipped > 100 en 60s → caméra vibrante ou bougée → vérifier montage
    """
    _emit("blur_rejection", {
        "camera_id": camera_id,
        "camera_name": camera_name,
        "laplacian_variance": round(sharpness, 2),
        "blur_threshold": threshold,
        "total_frames_skipped": total_skipped,
    })
